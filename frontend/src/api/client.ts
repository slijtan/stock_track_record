import axios, { AxiosError } from 'axios';
import type {
  Channel,
  ChannelStock,
  TimelineItem,
  ProcessingLog,
  StockMention,
  PaginatedResponse
} from '../types';

const API_BASE_URL = import.meta.env.VITE_API_URL || '/api';

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
  timeout: 30000,
});

// Custom error class for API errors
export class ApiError extends Error {
  status: number;
  detail: string;

  constructor(message: string, status: number, detail: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.detail = detail;
  }
}

// Retry configuration
const MAX_RETRIES = 3;
const RETRY_DELAY = 1000;

async function withRetry<T>(
  fn: () => Promise<T>,
  retries = MAX_RETRIES
): Promise<T> {
  try {
    return await fn();
  } catch (error) {
    const axiosError = error as AxiosError;

    // Don't retry on client errors (4xx) except 429 (rate limit)
    if (axiosError.response?.status &&
        axiosError.response.status >= 400 &&
        axiosError.response.status < 500 &&
        axiosError.response.status !== 429) {
      throw error;
    }

    if (retries > 0) {
      await new Promise(resolve => setTimeout(resolve, RETRY_DELAY));
      return withRetry(fn, retries - 1);
    }
    throw error;
  }
}

// Error handler
function handleError(error: unknown): never {
  if (axios.isAxiosError(error)) {
    const axiosError = error as AxiosError<{ detail?: string }>;
    const status = axiosError.response?.status || 500;
    const detail = axiosError.response?.data?.detail || axiosError.message;

    if (status === 404) {
      throw new ApiError('Not found', status, detail);
    }
    if (status === 429) {
      throw new ApiError('Too many requests. Please try again later.', status, detail);
    }
    if (status >= 500) {
      throw new ApiError('Server error. Please try again later.', status, detail);
    }
    throw new ApiError(detail, status, detail);
  }
  throw error;
}

// Channel endpoints
export const channelApi = {
  list: async (page = 1, perPage = 20): Promise<PaginatedResponse<Channel>> => {
    try {
      const response = await withRetry(() =>
        api.get('/channels', { params: { page, per_page: perPage } })
      );
      return response.data;
    } catch (error) {
      handleError(error);
    }
  },

  get: async (id: string): Promise<Channel> => {
    try {
      const response = await withRetry(() => api.get(`/channels/${id}`));
      return response.data;
    } catch (error) {
      handleError(error);
    }
  },

  create: async (url: string, timeRangeMonths = 12): Promise<Channel> => {
    try {
      const response = await api.post('/channels', { url, time_range_months: timeRangeMonths });
      return response.data;
    } catch (error) {
      handleError(error);
    }
  },

  delete: async (id: string): Promise<void> => {
    try {
      await api.delete(`/channels/${id}`);
    } catch (error) {
      handleError(error);
    }
  },

  cancel: async (id: string): Promise<Channel> => {
    try {
      const response = await api.post(`/channels/${id}/cancel`);
      return response.data;
    } catch (error) {
      handleError(error);
    }
  },

  getStocks: async (id: string): Promise<ChannelStock[]> => {
    try {
      const response = await withRetry(() => api.get(`/channels/${id}/stocks`));
      return response.data.stocks;
    } catch (error) {
      handleError(error);
    }
  },

  getTimeline: async (id: string): Promise<TimelineItem[]> => {
    try {
      const response = await withRetry(() => api.get(`/channels/${id}/timeline`));
      return response.data.timeline;
    } catch (error) {
      handleError(error);
    }
  },

  getLogs: async (id: string, since?: string): Promise<ProcessingLog[]> => {
    try {
      const response = await api.get(`/channels/${id}/logs`, { params: { since } });
      return response.data.logs;
    } catch (error) {
      handleError(error);
    }
  },

  getStockDrilldown: async (channelId: string, ticker: string): Promise<StockMention[]> => {
    try {
      const response = await withRetry(() => api.get(`/channels/${channelId}/stocks/${ticker}`));
      return response.data.mentions;
    } catch (error) {
      handleError(error);
    }
  },

  refreshPrices: async (channelId: string): Promise<{ prices: Record<string, number>; updated_at: string }> => {
    try {
      const response = await api.post(`/channels/${channelId}/refresh-prices`);
      return response.data;
    } catch (error) {
      handleError(error);
    }
  },

  backfillPrices: async (channelId: string): Promise<{ updated: number; total: number }> => {
    try {
      const response = await api.post(`/channels/${channelId}/backfill-prices`);
      return response.data;
    } catch (error) {
      handleError(error);
    }
  },
};

// Stock endpoints
export const stockApi = {
  getPrice: async (ticker: string): Promise<{ ticker: string; price: number; updated_at: string }> => {
    try {
      const response = await withRetry(() => api.get(`/stocks/${ticker}/price`));
      return response.data;
    } catch (error) {
      handleError(error);
    }
  },
};

export default api;
