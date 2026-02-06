const CACHE_KEY = 'stock_prices_cache';
const CACHE_TTL_MS = 24 * 60 * 60 * 1000; // 1 day

interface CacheEntry {
  prices: Record<string, number>;
  timestamp: number;
}

interface PriceCache {
  [channelId: string]: CacheEntry;
}

export function getCachedPrices(channelId: string): Record<string, number> | null {
  try {
    const cacheStr = localStorage.getItem(CACHE_KEY);
    if (!cacheStr) return null;

    const cache: PriceCache = JSON.parse(cacheStr);
    const entry = cache[channelId];

    if (!entry) return null;

    // Check if cache is expired
    if (Date.now() - entry.timestamp > CACHE_TTL_MS) {
      // Remove expired entry
      delete cache[channelId];
      localStorage.setItem(CACHE_KEY, JSON.stringify(cache));
      return null;
    }

    return entry.prices;
  } catch {
    return null;
  }
}

export function setCachedPrices(channelId: string, prices: Record<string, number>): void {
  try {
    const cacheStr = localStorage.getItem(CACHE_KEY);
    const cache: PriceCache = cacheStr ? JSON.parse(cacheStr) : {};

    cache[channelId] = {
      prices,
      timestamp: Date.now(),
    };

    localStorage.setItem(CACHE_KEY, JSON.stringify(cache));
  } catch {
    // Ignore cache errors
  }
}

export function clearPriceCache(channelId?: string): void {
  try {
    if (channelId) {
      const cacheStr = localStorage.getItem(CACHE_KEY);
      if (cacheStr) {
        const cache: PriceCache = JSON.parse(cacheStr);
        delete cache[channelId];
        localStorage.setItem(CACHE_KEY, JSON.stringify(cache));
      }
    } else {
      localStorage.removeItem(CACHE_KEY);
    }
  } catch {
    // Ignore cache errors
  }
}
