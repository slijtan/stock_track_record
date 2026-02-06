import { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
} from 'chart.js';
import { Line } from 'react-chartjs-2';
import { channelApi, stockApi } from '../api/client';
import type { StockMention, Channel } from '../types';
import SentimentBadge from '../components/SentimentBadge';

ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend
);

export default function StockDrilldown() {
  const { id, ticker } = useParams<{ id: string; ticker: string }>();
  const [channel, setChannel] = useState<Channel | null>(null);
  const [mentions, setMentions] = useState<StockMention[]>([]);
  const [currentPrice, setCurrentPrice] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!id || !ticker) return;

    const fetchData = async () => {
      try {
        setLoading(true);
        const [channelData, mentionsData, priceData] = await Promise.all([
          channelApi.get(id),
          channelApi.getStockDrilldown(id, ticker),
          stockApi.getPrice(ticker).catch(() => null),
        ]);
        setChannel(channelData);
        // Sort mentions from oldest to newest
        const sortedMentions = [...mentionsData].sort((a, b) => {
          const dateA = new Date(a.video?.published_at || a.created_at).getTime();
          const dateB = new Date(b.video?.published_at || b.created_at).getTime();
          return dateA - dateB;
        });
        setMentions(sortedMentions);
        setCurrentPrice(priceData?.price || null);
        setError(null);
      } catch (err) {
        setError('Failed to load stock details');
        console.error(err);
      } finally {
        setLoading(false);
      }
    };

    fetchData();
  }, [id, ticker]);

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
        {error || 'Stock not found'}
      </div>
    );
  }

  const sentimentColors = {
    buy: 'rgb(34, 197, 94)',
    hold: 'rgb(234, 179, 8)',
    sell: 'rgb(239, 68, 68)',
    mentioned: 'rgb(59, 130, 246)',
  };

  // Build chart data with optional "Today" datapoint
  const chartLabels = mentions.map(m => new Date(m.video?.published_at || m.created_at).toLocaleDateString());
  const chartPrices = mentions.map(m => m.price_at_mention || 0);
  const chartColors = mentions.map(m => sentimentColors[m.sentiment]);

  // Add today's price as final datapoint if available
  if (currentPrice) {
    chartLabels.push('Today');
    chartPrices.push(currentPrice);
    chartColors.push('rgb(0, 0, 0)'); // Black for today
  }

  const chartData = {
    labels: chartLabels,
    datasets: [
      {
        label: 'Price at Mention',
        data: chartPrices,
        borderColor: 'rgb(75, 85, 99)',
        backgroundColor: chartColors,
        pointRadius: 8,
        pointHoverRadius: 10,
        tension: 0.1,
      },
    ],
  };

  const chartOptions = {
    responsive: true,
    plugins: {
      legend: {
        display: false,
      },
      tooltip: {
        callbacks: {
          label: (context: { dataIndex: number; parsed: { y: number | null } }) => {
            const price = context.parsed.y ?? 0;
            // Check if this is the "Today" datapoint
            if (currentPrice && context.dataIndex === mentions.length) {
              return [`Current Price: $${price.toFixed(2)}`];
            }
            const mention = mentions[context.dataIndex];
            return [
              `Price: $${price.toFixed(2)}`,
              `Sentiment: ${mention.sentiment.toUpperCase()}`,
              `Video: ${mention.video?.title || 'Unknown'}`,
            ];
          },
        },
      },
    },
    scales: {
      y: {
        title: {
          display: true,
          text: 'Price ($)',
        },
      },
    },
  } as const;

  return (
    <div>
      <Link to={`/channels/${id}`} className="text-blue-600 hover:text-blue-700 mb-4 inline-block">
        &larr; Back to {channel.name}
      </Link>

      <div className="bg-white rounded-lg shadow p-6 mb-6">
        <div className="flex justify-between items-start">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">{ticker}</h1>
            {currentPrice && (
              <p className="text-xl text-gray-600 mt-1">${currentPrice.toFixed(2)}</p>
            )}
          </div>
          <a
            href={`https://finance.yahoo.com/quote/${ticker}`}
            target="_blank"
            rel="noopener noreferrer"
            className="text-blue-600 hover:text-blue-700"
          >
            Yahoo Finance &rarr;
          </a>
        </div>
      </div>

      {/* Chart */}
      <div className="bg-white rounded-lg shadow p-6 mb-6">
        <h2 className="text-lg font-semibold text-gray-900 mb-4">Price Chart with Mentions</h2>
        <Line data={chartData} options={chartOptions} />
        <div className="flex justify-center space-x-4 mt-4 text-sm">
          <span className="flex items-center"><span className="w-3 h-3 rounded-full bg-green-500 mr-1"></span> Buy</span>
          <span className="flex items-center"><span className="w-3 h-3 rounded-full bg-yellow-500 mr-1"></span> Hold</span>
          <span className="flex items-center"><span className="w-3 h-3 rounded-full bg-red-500 mr-1"></span> Sell</span>
          <span className="flex items-center"><span className="w-3 h-3 rounded-full bg-blue-500 mr-1"></span> Mentioned</span>
          <span className="flex items-center"><span className="w-3 h-3 rounded-full bg-black mr-1"></span> Today</span>
        </div>
      </div>

      {/* All Mentions */}
      <div className="bg-white rounded-lg shadow">
        <div className="px-6 py-4 border-b border-gray-200">
          <h2 className="text-lg font-semibold text-gray-900">All Mentions</h2>
        </div>
        <div className="divide-y divide-gray-200">
          {mentions.map((mention) => (
            <div key={mention.id} className="px-6 py-4">
              <div className="flex justify-between items-start">
                <div className="flex-1">
                  <div className="flex items-center space-x-2">
                    <SentimentBadge ticker={ticker!} sentiment={mention.sentiment} />
                    <span className="text-gray-500">
                      @ ${mention.price_at_mention?.toFixed(2) || '-'}
                    </span>
                  </div>
                  {mention.video && (
                    <a
                      href={mention.video.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-sm text-blue-600 hover:text-blue-700 mt-1 block"
                    >
                      {mention.video.title}
                    </a>
                  )}
                  {mention.context_snippet && (
                    <p className="text-sm text-gray-500 mt-1 italic">
                      "{mention.context_snippet}"
                    </p>
                  )}
                </div>
                <span className="text-sm text-gray-400">
                  {new Date(mention.video?.published_at || mention.created_at).toLocaleDateString()}
                </span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
