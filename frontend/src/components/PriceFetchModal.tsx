import { useEffect, useRef } from 'react';

export type TickerStatus = 'queued' | 'fetching' | 'success' | 'error';

export interface TickerFetchState {
  ticker: string;
  status: TickerStatus;
  price?: number;
  error?: string;
}

interface PriceFetchModalProps {
  isOpen: boolean;
  onClose: () => void;
  tickers: TickerFetchState[];
}

export default function PriceFetchModal({ isOpen, onClose, tickers }: PriceFetchModalProps) {
  const modalRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    if (isOpen) {
      document.addEventListener('keydown', handleEscape);
    }
    return () => document.removeEventListener('keydown', handleEscape);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  const completed = tickers.filter(t => t.status === 'success').length;
  const failed = tickers.filter(t => t.status === 'error').length;
  const fetching = tickers.filter(t => t.status === 'fetching').length;
  const queued = tickers.filter(t => t.status === 'queued').length;
  const total = tickers.length;

  const getStatusIcon = (status: TickerStatus) => {
    switch (status) {
      case 'queued': return <span className="text-gray-400">○</span>;
      case 'fetching': return <span className="text-blue-500 animate-pulse">◉</span>;
      case 'success': return <span className="text-green-500">✓</span>;
      case 'error': return <span className="text-red-500">✗</span>;
    }
  };

  const getStatusColor = (status: TickerStatus) => {
    switch (status) {
      case 'queued': return 'text-gray-500';
      case 'fetching': return 'text-blue-600';
      case 'success': return 'text-green-600';
      case 'error': return 'text-red-600';
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/50"
        onClick={onClose}
      />

      {/* Modal */}
      <div
        ref={modalRef}
        className="relative bg-white rounded-lg shadow-xl w-96 max-h-[80vh] flex flex-col"
      >
        {/* Header */}
        <div className="px-4 py-3 border-b border-gray-200 flex justify-between items-center">
          <h3 className="text-lg font-semibold text-gray-900">Fetching Prices</h3>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 text-xl leading-none"
          >
            &times;
          </button>
        </div>

        {/* Progress Summary */}
        <div className="px-4 py-3 bg-gray-50 border-b border-gray-200">
          <div className="flex justify-between text-sm mb-2">
            <span className="text-gray-600">Progress</span>
            <span className="font-medium">{completed + failed}/{total}</span>
          </div>
          <div className="w-full bg-gray-200 rounded-full h-2">
            <div
              className="bg-blue-600 h-2 rounded-full transition-all duration-300"
              style={{ width: `${((completed + failed) / total) * 100}%` }}
            />
          </div>
          <div className="flex gap-4 mt-2 text-xs">
            <span className="text-green-600">{completed} loaded</span>
            <span className="text-red-600">{failed} failed</span>
            <span className="text-blue-600">{fetching} fetching</span>
            <span className="text-gray-500">{queued} queued</span>
          </div>
        </div>

        {/* Ticker List */}
        <div className="flex-1 overflow-y-auto px-2 py-2">
          <div className="space-y-1">
            {tickers.map(({ ticker, status, price, error }) => (
              <div
                key={ticker}
                className={`flex items-center justify-between px-2 py-1.5 rounded ${
                  status === 'fetching' ? 'bg-blue-50' : ''
                }`}
              >
                <div className="flex items-center gap-2">
                  {getStatusIcon(status)}
                  <span className={`font-mono text-sm ${getStatusColor(status)}`}>
                    {ticker}
                  </span>
                </div>
                <div className="text-sm">
                  {status === 'success' && price && (
                    <span className="text-green-600 font-medium">${price.toFixed(2)}</span>
                  )}
                  {status === 'fetching' && (
                    <span className="text-blue-500 text-xs">fetching...</span>
                  )}
                  {status === 'queued' && (
                    <span className="text-gray-400 text-xs">queued</span>
                  )}
                  {status === 'error' && (
                    <span className="text-red-500 text-xs" title={error}>failed</span>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Footer */}
        <div className="px-4 py-3 border-t border-gray-200 bg-gray-50">
          <p className="text-xs text-gray-500">
            Finnhub API rate limit: 60 requests/min. Fetching sequentially.
          </p>
        </div>
      </div>
    </div>
  );
}
