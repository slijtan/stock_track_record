export type ChannelStatus = 'pending' | 'processing' | 'completed' | 'failed' | 'cancelled';
export type Sentiment = 'buy' | 'hold' | 'sell' | 'mentioned';
export type LogLevel = 'info' | 'warning' | 'error';

export interface Channel {
  id: string;
  youtube_channel_id: string;
  name: string;
  url: string;
  thumbnail_url?: string;
  status: ChannelStatus;
  video_count: number;
  processed_video_count: number;
  time_range_months: number;
  created_at: string;
  updated_at: string;
}

export interface Video {
  id: string;
  channel_id: string;
  youtube_video_id: string;
  title: string;
  url: string;
  published_at: string;
  transcript_status: string;
  analysis_status: string;
  created_at: string;
}

export interface Stock {
  ticker: string;
  name?: string;
  exchange: 'NYSE' | 'NASDAQ';
  last_price?: number;
  price_updated_at?: string;
}

export interface StockMention {
  id: string;
  video_id: string;
  ticker: string;
  sentiment: Sentiment;
  price_at_mention?: number;
  confidence_score?: number;
  context_snippet?: string;
  created_at: string;
  video?: Video;
}

export interface ProcessingLog {
  id: number;
  channel_id: string;
  log_level: LogLevel;
  message: string;
  created_at: string;
}

export interface ChannelStock {
  ticker: string;
  name?: string;
  first_mention_date: string;
  first_mention_video_id: string;
  first_mention_video_title: string;
  price_at_first_mention?: number;
  current_price?: number;
  price_change_percent?: number;
  buy_count: number;
  hold_count: number;
  sell_count: number;
  mentioned_count: number;
  total_mentions: number;
  yahoo_finance_url: string;
}

export interface TimelineItem {
  video: Video;
  mentions: StockMention[];
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  per_page: number;
}
