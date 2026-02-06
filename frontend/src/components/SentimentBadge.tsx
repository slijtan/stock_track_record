import { Link } from 'react-router-dom';
import type { Sentiment } from '../types';

interface SentimentBadgeProps {
  ticker: string;
  sentiment: Sentiment;
  linkTo?: string;
}

export default function SentimentBadge({ ticker, sentiment, linkTo }: SentimentBadgeProps) {
  const styles = {
    buy: 'bg-green-100 text-green-800 border-green-200',
    hold: 'bg-yellow-100 text-yellow-800 border-yellow-200',
    sell: 'bg-red-100 text-red-800 border-red-200',
    mentioned: 'bg-blue-100 text-blue-800 border-blue-200',
  };

  const icons = {
    buy: '🟢',
    hold: '🟡',
    sell: '🔴',
    mentioned: '🔵',
  };

  const content = (
    <span className={`inline-flex items-center px-2 py-1 rounded border text-sm ${styles[sentiment]}`}>
      <span className="mr-1">{icons[sentiment]}</span>
      {ticker}
    </span>
  );

  if (linkTo) {
    return (
      <Link to={linkTo} className="hover:opacity-80 transition-opacity">
        {content}
      </Link>
    );
  }

  return content;
}
