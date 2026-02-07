from datetime import datetime, date
from typing import Optional, List
from pydantic import BaseModel


class StockMentionResponse(BaseModel):
    id: str
    video_id: str
    ticker: str
    sentiment: str
    price_at_mention: Optional[float] = None
    confidence_score: Optional[float] = None
    context_snippet: Optional[str] = None
    created_at: datetime
    video: Optional["VideoResponse"] = None



class VideoResponse(BaseModel):
    id: str
    channel_id: str
    youtube_video_id: str
    title: str
    url: str
    published_at: date
    transcript_status: str
    analysis_status: str
    created_at: datetime



class ChannelStockResponse(BaseModel):
    ticker: str
    name: Optional[str] = None
    first_mention_date: date
    first_mention_video_id: str
    first_mention_video_title: str
    price_at_first_mention: Optional[float] = None
    current_price: Optional[float] = None
    price_change_percent: Optional[float] = None
    buy_count: int
    hold_count: int
    sell_count: int
    mentioned_count: int
    total_mentions: int
    yahoo_finance_url: str


class ChannelStocksResponse(BaseModel):
    channel_id: str
    stocks: List[ChannelStockResponse]


class TimelineItem(BaseModel):
    video: VideoResponse
    mentions: List[StockMentionResponse]


class TimelineResponse(BaseModel):
    timeline: List[TimelineItem]


class StockDrilldownResponse(BaseModel):
    ticker: str
    channel_id: str
    mentions: List[StockMentionResponse]


class StockPriceResponse(BaseModel):
    ticker: str
    price: Optional[float] = None
    updated_at: Optional[datetime] = None
    error: Optional[str] = None


class BatchPricesResponse(BaseModel):
    prices: dict[str, float]
    updated_at: datetime


# Update forward references
StockMentionResponse.model_rebuild()
