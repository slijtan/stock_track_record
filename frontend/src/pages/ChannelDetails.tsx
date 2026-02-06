import { useState, useEffect, useCallback } from 'react';
import { useParams, Link } from 'react-router-dom';
import { channelApi, stockApi } from '../api/client';
import type { Channel, ChannelStock, TimelineItem, ProcessingLog } from '../types';
import ProcessingProgress from '../components/ProcessingProgress';
import SentimentBadge from '../components/SentimentBadge';
import PriceFetchModal from '../components/PriceFetchModal';
import type { TickerFetchState } from '../components/PriceFetchModal';
import { getCachedPrices, setCachedPrices } from '../utils/priceCache';

type Tab = 'timeline' | 'stocks';
type SortColumn = 'ticker' | 'first_mention_date' | 'price_change_percent';
type SortDirection = 'asc' | 'desc';

export default function ChannelDetails() {
  const { id } = useParams<{ id: string }>();
  const [channel, setChannel] = useState<Channel | null>(null);
  const [stocks, setStocks] = useState<ChannelStock[]>([]);
  const [timeline, setTimeline] = useState<TimelineItem[]>([]);
  const [logs, setLogs] = useState<ProcessingLog[]>([]);
  const [activeTab, setActiveTab] = useState<Tab>('stocks');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [pricesLoading, setPricesLoading] = useState(false);
  const [pricesError, setPricesError] = useState(false);
  const [sortColumn, setSortColumn] = useState<SortColumn>('ticker');
  const [sortDirection, setSortDirection] = useState<SortDirection>('asc');
  const [tickerStates, setTickerStates] = useState<TickerFetchState[]>([]);
  const [showPriceModal, setShowPriceModal] = useState(false);

  const handleSort = (column: SortColumn) => {
    if (sortColumn === column) {
      setSortDirection(prev => prev === 'asc' ? 'desc' : 'asc');
    } else {
      setSortColumn(column);
      setSortDirection('asc');
    }
  };

  const sortedStocks = [...stocks].sort((a, b) => {
    let comparison = 0;
    switch (sortColumn) {
      case 'ticker':
        comparison = a.ticker.localeCompare(b.ticker);
        break;
      case 'first_mention_date':
        comparison = new Date(a.first_mention_date).getTime() - new Date(b.first_mention_date).getTime();
        break;
      case 'price_change_percent': {
        const aChange = a.price_change_percent ?? -Infinity;
        const bChange = b.price_change_percent ?? -Infinity;
        comparison = aChange - bChange;
        break;
      }
    }
    return sortDirection === 'asc' ? comparison : -comparison;
  });

  const SortIndicator = ({ column }: { column: SortColumn }) => {
    if (sortColumn !== column) return <span className="text-gray-300 ml-1">↕</span>;
    return <span className="ml-1">{sortDirection === 'asc' ? '↑' : '↓'}</span>;
  };

  const refreshPrices = useCallback(async (tickerList?: string[]) => {
    if (!id || pricesLoading) return;

    const tickers = tickerList || stocks.map(s => s.ticker);
    if (tickers.length === 0) return;

    setPricesLoading(true);
    setPricesError(false);
    setShowPriceModal(true);

    // Initialize all tickers as queued
    const initialStates: TickerFetchState[] = tickers.map(ticker => ({
      ticker,
      status: 'queued',
    }));
    setTickerStates(initialStates);

    const prices: Record<string, number> = {};

    // Fetch prices individually
    for (let i = 0; i < tickers.length; i++) {
      const ticker = tickers[i];

      // Update status to fetching
      setTickerStates(prev => prev.map(t =>
        t.ticker === ticker ? { ...t, status: 'fetching' } : t
      ));

      try {
        const result = await stockApi.getPrice(ticker);
        if (result.price) {
          prices[ticker] = result.price;
          setTickerStates(prev => prev.map(t =>
            t.ticker === ticker ? { ...t, status: 'success', price: result.price } : t
          ));

          // Update stock in list immediately
          setStocks(prev => prev.map(stock => {
            if (stock.ticker !== ticker) return stock;
            const newPrice = result.price;
            return {
              ...stock,
              current_price: newPrice,
              price_change_percent: stock.price_at_first_mention
                ? ((newPrice - stock.price_at_first_mention) / stock.price_at_first_mention) * 100
                : stock.price_change_percent,
            };
          }));
        } else {
          setTickerStates(prev => prev.map(t =>
            t.ticker === ticker ? { ...t, status: 'error', error: 'No price data' } : t
          ));
        }
      } catch (err) {
        setTickerStates(prev => prev.map(t =>
          t.ticker === ticker ? { ...t, status: 'error', error: String(err) } : t
        ));
      }

      // Small delay to avoid rate limiting (handled server-side, but be safe)
      if (i < tickers.length - 1) {
        await new Promise(resolve => setTimeout(resolve, 100));
      }
    }

    // Cache the prices
    if (Object.keys(prices).length > 0) {
      setCachedPrices(id, prices);
    } else {
      setPricesError(true);
    }

    setPricesLoading(false);
  }, [id, pricesLoading, stocks]);

  useEffect(() => {
    if (!id) return;

    const fetchData = async () => {
      try {
        setLoading(true);
        const channelData = await channelApi.get(id);
        setChannel(channelData);

        if (channelData.status === 'completed' || channelData.status === 'cancelled') {
          const [stocksData, timelineData] = await Promise.all([
            channelApi.getStocks(id),
            channelApi.getTimeline(id),
          ]);

          // Check cache for current prices (must have actual prices, not empty)
          const cachedPrices = getCachedPrices(id);
          const hasCachedPrices = cachedPrices && Object.keys(cachedPrices).length > 0;

          if (hasCachedPrices) {
            // Apply cached prices to stocks
            const updatedStocks = stocksData.map(stock => ({
              ...stock,
              current_price: cachedPrices[stock.ticker] ?? stock.current_price,
              price_change_percent: cachedPrices[stock.ticker] && stock.price_at_first_mention
                ? ((cachedPrices[stock.ticker] - stock.price_at_first_mention) / stock.price_at_first_mention) * 100
                : stock.price_change_percent,
            }));
            setStocks(updatedStocks);
          } else {
            setStocks(stocksData);

            // Fetch fresh prices if not cached
            if (stocksData.length > 0) {
              // Trigger price fetch after a small delay to let state settle
              const tickers = stocksData.map(s => s.ticker);
              setTimeout(() => refreshPrices(tickers), 100);

              // Also backfill any missing historical prices
              channelApi.backfillPrices(id).catch(console.error);
            }
          }
          setTimeline(timelineData);
        } else if (channelData.status === 'processing' || channelData.status === 'pending') {
          // Fetch logs for both processing and pending status
          const logsData = await channelApi.getLogs(id);
          setLogs(logsData);
        }
        setError(null);
      } catch (err) {
        setError('Failed to load channel details');
        console.error(err);
      } finally {
        setLoading(false);
      }
    };

    fetchData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  // Poll for updates if processing or pending
  useEffect(() => {
    if (!id || (channel?.status !== 'processing' && channel?.status !== 'pending')) return;

    const interval = setInterval(async () => {
      try {
        const [channelData, logsData] = await Promise.all([
          channelApi.get(id),
          channelApi.getLogs(id),
        ]);
        setChannel(channelData);
        setLogs(logsData);

        if (channelData.status === 'completed' || channelData.status === 'cancelled') {
          const [stocksData, timelineData] = await Promise.all([
            channelApi.getStocks(id),
            channelApi.getTimeline(id),
          ]);
          setStocks(stocksData);
          setTimeline(timelineData);
        }
      } catch (err) {
        console.error(err);
      }
    }, 2000);

    return () => clearInterval(interval);
  }, [id, channel?.status]);

  if (loading) {
    return (
      <div className="flex justify-center items-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  if (error || !channel) {
    return (
      <div className="bg-red-50 text-red-700 p-4 rounded-lg">
        {error || 'Channel not found'}
      </div>
    );
  }

  if (channel.status === 'processing' || channel.status === 'pending') {
    return (
      <div>
        <Link to="/" className="text-blue-600 hover:text-blue-700 mb-4 inline-block">
          &larr; Back to channels
        </Link>
        <ProcessingProgress channel={channel} logs={logs} />
      </div>
    );
  }

  return (
    <div>
      <Link to="/" className="text-blue-600 hover:text-blue-700 mb-4 inline-block">
        &larr; Back to channels
      </Link>

      <div className="bg-white rounded-lg shadow p-6 mb-6">
        <h1 className="text-2xl font-bold text-gray-900">{channel.name}</h1>
        <div className="flex items-center gap-4 mt-1">
          <p className="text-gray-500">
            {channel.video_count} videos analyzed
          </p>
          {pricesLoading && (
            <button
              onClick={() => setShowPriceModal(true)}
              className="text-blue-600 text-sm hover:text-blue-700"
            >
              (refreshing prices... {tickerStates.filter(t => t.status === 'success').length}/{tickerStates.length}) - click for details
            </button>
          )}
          {pricesError && (
            <button
              onClick={() => refreshPrices()}
              className="text-sm text-blue-600 hover:text-blue-700 underline"
            >
              Retry loading prices
            </button>
          )}
          {!pricesLoading && !pricesError && (
            <button
              onClick={() => refreshPrices()}
              className="text-sm text-gray-500 hover:text-gray-700"
              title="Refresh current prices"
            >
              ↻ Refresh prices
            </button>
          )}
        </div>
      </div>

      {/* Tabs */}
      <div className="border-b border-gray-200 mb-6">
        <nav className="flex space-x-8">
          <button
            onClick={() => setActiveTab('stocks')}
            className={`py-4 px-1 border-b-2 font-medium text-sm ${
              activeTab === 'stocks'
                ? 'border-blue-500 text-blue-600'
                : 'border-transparent text-gray-500 hover:text-gray-700'
            }`}
          >
            Stocks
          </button>
          <button
            onClick={() => setActiveTab('timeline')}
            className={`py-4 px-1 border-b-2 font-medium text-sm ${
              activeTab === 'timeline'
                ? 'border-blue-500 text-blue-600'
                : 'border-transparent text-gray-500 hover:text-gray-700'
            }`}
          >
            Timeline
          </button>
        </nav>
      </div>

      {/* Stocks Tab */}
      {activeTab === 'stocks' && (
        <div className="bg-white rounded-lg shadow overflow-hidden">
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gray-50">
                <tr>
                  <th
                    className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase cursor-pointer hover:bg-gray-100 select-none"
                    onClick={() => handleSort('ticker')}
                  >
                    Ticker<SortIndicator column="ticker" />
                  </th>
                  <th
                    className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase cursor-pointer hover:bg-gray-100 select-none"
                    onClick={() => handleSort('first_mention_date')}
                  >
                    First Pick<SortIndicator column="first_mention_date" />
                  </th>
                  <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase">Then</th>
                  <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase">Now</th>
                  <th
                    className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase cursor-pointer hover:bg-gray-100 select-none"
                    onClick={() => handleSort('price_change_percent')}
                  >
                    Change<SortIndicator column="price_change_percent" />
                  </th>
                  <th className="px-6 py-3 text-center text-xs font-medium text-gray-500 uppercase">Mentions</th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-200">
                {sortedStocks.map((stock) => (
                  <tr key={stock.ticker} className="hover:bg-gray-50">
                    <td className="px-6 py-4 whitespace-nowrap">
                      <Link
                        to={`/channels/${id}/stocks/${stock.ticker}`}
                        className="text-blue-600 hover:text-blue-700 font-medium"
                      >
                        {stock.ticker}
                      </Link>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                      {new Date(stock.first_mention_date).toLocaleDateString()}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-right">
                      ${stock.price_at_first_mention?.toFixed(2) || '-'}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-right">
                      ${stock.current_price?.toFixed(2) || '-'}
                    </td>
                    <td className={`px-6 py-4 whitespace-nowrap text-sm text-right font-medium ${
                      (stock.price_change_percent ?? 0) >= 0 ? 'text-green-600' : 'text-red-600'
                    }`}>
                      {stock.price_change_percent != null
                        ? `${stock.price_change_percent >= 0 ? '+' : ''}${stock.price_change_percent.toFixed(2)}%`
                        : '-'}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-center">
                      <div className="flex justify-center space-x-2 text-xs">
                        {stock.buy_count > 0 && <span className="text-green-600">{stock.buy_count} buy</span>}
                        {stock.hold_count > 0 && <span className="text-yellow-600">{stock.hold_count} hold</span>}
                        {stock.sell_count > 0 && <span className="text-red-600">{stock.sell_count} sell</span>}
                        {stock.mentioned_count > 0 && <span className="text-blue-600">{stock.mentioned_count} mentioned</span>}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Timeline Tab */}
      {activeTab === 'timeline' && (
        <div className="space-y-4">
          {/* Color Key Legend */}
          <div className="bg-white rounded-lg shadow p-4">
            <div className="flex flex-wrap items-center gap-4 text-sm">
              <span className="font-medium text-gray-700">Legend:</span>
              <span className="inline-flex items-center gap-1">
                <span className="inline-flex items-center px-2 py-1 rounded border bg-green-100 text-green-800 border-green-200 text-xs">
                  <span className="mr-1">🟢</span>BUY
                </span>
                <span className="text-gray-500">Recommended to buy</span>
              </span>
              <span className="inline-flex items-center gap-1">
                <span className="inline-flex items-center px-2 py-1 rounded border bg-yellow-100 text-yellow-800 border-yellow-200 text-xs">
                  <span className="mr-1">🟡</span>HOLD
                </span>
                <span className="text-gray-500">Recommended to hold</span>
              </span>
              <span className="inline-flex items-center gap-1">
                <span className="inline-flex items-center px-2 py-1 rounded border bg-red-100 text-red-800 border-red-200 text-xs">
                  <span className="mr-1">🔴</span>SELL
                </span>
                <span className="text-gray-500">Recommended to sell</span>
              </span>
              <span className="inline-flex items-center gap-1">
                <span className="inline-flex items-center px-2 py-1 rounded border bg-blue-100 text-blue-800 border-blue-200 text-xs">
                  <span className="mr-1">🔵</span>MENTIONED
                </span>
                <span className="text-gray-500">Discussed without recommendation</span>
              </span>
            </div>
          </div>
          {timeline.map((item) => (
            <div key={item.video.id} className="bg-white rounded-lg shadow p-4">
              <div className="flex justify-between items-start mb-2">
                <div>
                  <a
                    href={item.video.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-lg font-medium text-gray-900 hover:text-blue-600"
                  >
                    {item.video.title}
                  </a>
                  <p className="text-sm text-gray-500">
                    {new Date(item.video.published_at).toLocaleDateString()}
                  </p>
                </div>
              </div>
              <div className="flex flex-wrap gap-2">
                {item.mentions.map((mention) => (
                  <SentimentBadge
                    key={mention.id}
                    ticker={mention.ticker}
                    sentiment={mention.sentiment}
                    linkTo={`/channels/${id}/stocks/${mention.ticker}`}
                  />
                ))}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Price Fetch Modal */}
      <PriceFetchModal
        isOpen={showPriceModal}
        onClose={() => setShowPriceModal(false)}
        tickers={tickerStates}
      />
    </div>
  );
}
