import { useRef, useEffect, useState } from 'react';
import { channelApi } from '../api/client';
import type { Channel, ProcessingLog } from '../types';

interface ProcessingProgressProps {
  channel: Channel;
  logs: ProcessingLog[];
  onCancelled?: () => void;
}

export default function ProcessingProgress({ channel, logs, onCancelled }: ProcessingProgressProps) {
  const logsEndRef = useRef<HTMLDivElement>(null);
  const [cancelling, setCancelling] = useState(false);

  useEffect(() => {
    logsEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [logs]);

  const handleCancel = async () => {
    if (!confirm('Are you sure you want to cancel processing?')) {
      return;
    }
    try {
      setCancelling(true);
      await channelApi.cancel(channel.id);
      onCancelled?.();
    } catch (err) {
      console.error('Failed to cancel:', err);
      setCancelling(false);
    }
  };

  const progress = channel.video_count > 0
    ? (channel.processed_video_count / channel.video_count) * 100
    : 0;

  const getLogStyle = (level: string) => {
    switch (level) {
      case 'error':
        return 'text-red-600';
      case 'warning':
        return 'text-yellow-600';
      default:
        return 'text-gray-600';
    }
  };

  const getLogIcon = (level: string) => {
    switch (level) {
      case 'error':
        return '❌';
      case 'warning':
        return '⚠️';
      default:
        return '✓';
    }
  };

  return (
    <div className="bg-white rounded-lg shadow p-6">
      <div className="flex justify-between items-start mb-4">
        <h2 className="text-xl font-bold text-gray-900">
          Processing: {channel.name}
        </h2>
        {channel.status === 'processing' && (
          <button
            onClick={handleCancel}
            disabled={cancelling}
            className="px-3 py-1 text-sm bg-red-100 text-red-700 rounded hover:bg-red-200 disabled:opacity-50"
          >
            {cancelling ? 'Cancelling...' : 'Cancel'}
          </button>
        )}
      </div>

      {/* Progress Bar */}
      <div className="mb-6">
        <div className="flex justify-between text-sm text-gray-600 mb-2">
          <span>Progress</span>
          <span>
            {channel.processed_video_count} / {channel.video_count} videos ({progress.toFixed(0)}%)
          </span>
        </div>
        <div className="w-full bg-gray-200 rounded-full h-3">
          <div
            className="bg-blue-600 h-3 rounded-full transition-all duration-500"
            style={{ width: `${progress}%` }}
          ></div>
        </div>
      </div>

      {/* Live Log */}
      <div className="border border-gray-200 rounded-lg">
        <div className="bg-gray-50 px-4 py-2 border-b border-gray-200">
          <span className="text-sm font-medium text-gray-700">Live Log</span>
        </div>
        <div className="h-[calc(100vh-320px)] min-h-64 overflow-y-auto p-4 font-mono text-sm bg-gray-900 text-gray-100">
          {logs.map((log) => (
            <div key={log.id} className={`mb-1 ${getLogStyle(log.log_level)}`}>
              <span className="text-gray-500">
                [{new Date(log.created_at).toLocaleTimeString()}]
              </span>{' '}
              <span className="mr-1">{getLogIcon(log.log_level)}</span>
              {log.message}
            </div>
          ))}
          {channel.status === 'processing' && (
            <div className="animate-pulse text-blue-400">Processing...</div>
          )}
          {channel.status === 'completed' && (
            <div className="text-green-400">✓ Processing complete!</div>
          )}
          <div ref={logsEndRef} />
        </div>
      </div>
    </div>
  );
}
