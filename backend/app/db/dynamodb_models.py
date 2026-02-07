import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, date
from decimal import Decimal
from typing import Optional


def _utcnow_iso() -> str:
    """Return current UTC time as ISO 8601 string with Z suffix."""
    return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _parse_iso(iso_str: str) -> datetime:
    """Parse ISO 8601 string to datetime."""
    return datetime.fromisoformat(iso_str.replace("Z", "+00:00"))


def _parse_date(date_str: str) -> date:
    """Parse ISO date string to date object."""
    return date.fromisoformat(date_str)


def _log_sequence_id() -> int:
    """Generate a monotonically increasing integer ID from timestamp microseconds."""
    return int(time.time() * 1_000_000)


@dataclass
class Channel:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    youtube_channel_id: str = ""
    name: str = ""
    url: str = ""
    thumbnail_url: Optional[str] = None
    status: str = "pending"
    video_count: int = 0
    processed_video_count: int = 0
    time_range_months: int = 12
    created_at: str = field(default_factory=_utcnow_iso)
    updated_at: str = field(default_factory=_utcnow_iso)

    def to_item(self) -> dict:
        """Serialize to DynamoDB item with PK/SK/GSI keys."""
        item = {
            "PK": f"CHANNEL#{self.id}",
            "SK": f"CHANNEL#{self.id}",
            "GSI1PK": "CHANNELS",
            "GSI1SK": self.created_at,
            "GSI2PK": f"YT#{self.youtube_channel_id}",
            "entity_type": "Channel",
            "id": self.id,
            "youtube_channel_id": self.youtube_channel_id,
            "name": self.name,
            "url": self.url,
            "status": self.status,
            "video_count": self.video_count,
            "processed_video_count": self.processed_video_count,
            "time_range_months": self.time_range_months,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
        if self.thumbnail_url:
            item["thumbnail_url"] = self.thumbnail_url
        return item

    @classmethod
    def from_item(cls, item: dict) -> "Channel":
        """Deserialize from DynamoDB item."""
        return cls(
            id=item["id"],
            youtube_channel_id=item["youtube_channel_id"],
            name=item["name"],
            url=item["url"],
            thumbnail_url=item.get("thumbnail_url"),
            status=item["status"],
            video_count=int(item.get("video_count", 0)),
            processed_video_count=int(item.get("processed_video_count", 0)),
            time_range_months=int(item.get("time_range_months", 12)),
            created_at=item["created_at"],
            updated_at=item["updated_at"],
        )

    def to_response_dict(self) -> dict:
        """Convert to dict compatible with ChannelResponse Pydantic model."""
        return {
            "id": self.id,
            "youtube_channel_id": self.youtube_channel_id,
            "name": self.name,
            "url": self.url,
            "thumbnail_url": self.thumbnail_url,
            "status": self.status,
            "video_count": self.video_count,
            "processed_video_count": self.processed_video_count,
            "time_range_months": self.time_range_months,
            "created_at": _parse_iso(self.created_at),
            "updated_at": _parse_iso(self.updated_at),
        }


@dataclass
class Video:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    channel_id: str = ""
    youtube_video_id: str = ""
    title: str = ""
    url: str = ""
    published_at: str = ""  # ISO date string YYYY-MM-DD
    transcript_status: str = "pending"
    analysis_status: str = "pending"
    created_at: str = field(default_factory=_utcnow_iso)

    def to_item(self) -> dict:
        """Serialize to DynamoDB item."""
        return {
            "PK": f"CHANNEL#{self.channel_id}",
            "SK": f"VIDEO#{self.id}",
            "GSI3PK": f"YTVID#{self.youtube_video_id}",
            "entity_type": "Video",
            "id": self.id,
            "channel_id": self.channel_id,
            "youtube_video_id": self.youtube_video_id,
            "title": self.title,
            "url": self.url,
            "published_at": self.published_at,
            "transcript_status": self.transcript_status,
            "analysis_status": self.analysis_status,
            "created_at": self.created_at,
        }

    @classmethod
    def from_item(cls, item: dict) -> "Video":
        """Deserialize from DynamoDB item."""
        return cls(
            id=item["id"],
            channel_id=item["channel_id"],
            youtube_video_id=item["youtube_video_id"],
            title=item["title"],
            url=item["url"],
            published_at=item["published_at"],
            transcript_status=item.get("transcript_status", "pending"),
            analysis_status=item.get("analysis_status", "pending"),
            created_at=item["created_at"],
        )

    def to_response_dict(self) -> dict:
        """Convert to dict compatible with VideoResponse Pydantic model."""
        return {
            "id": self.id,
            "channel_id": self.channel_id,
            "youtube_video_id": self.youtube_video_id,
            "title": self.title,
            "url": self.url,
            "published_at": _parse_date(self.published_at),
            "transcript_status": self.transcript_status,
            "analysis_status": self.analysis_status,
            "created_at": _parse_iso(self.created_at),
        }


@dataclass
class Stock:
    ticker: str = ""
    name: Optional[str] = None
    exchange: str = "NYSE"
    last_price: Optional[float] = None
    price_updated_at: Optional[str] = None

    def to_item(self) -> dict:
        """Serialize to DynamoDB item for stocks table."""
        item = {
            "ticker": self.ticker,
            "exchange": self.exchange,
        }
        if self.name:
            item["name"] = self.name
        if self.last_price is not None:
            item["last_price"] = Decimal(str(self.last_price))
        if self.price_updated_at:
            item["price_updated_at"] = self.price_updated_at
        return item

    @classmethod
    def from_item(cls, item: dict) -> "Stock":
        """Deserialize from DynamoDB item."""
        last_price = item.get("last_price")
        return cls(
            ticker=item["ticker"],
            name=item.get("name"),
            exchange=item.get("exchange", "NYSE"),
            last_price=float(last_price) if last_price is not None else None,
            price_updated_at=item.get("price_updated_at"),
        )


@dataclass
class StockMention:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    video_id: str = ""
    ticker: str = ""
    sentiment: str = "mentioned"
    price_at_mention: Optional[float] = None
    confidence_score: Optional[float] = None
    context_snippet: Optional[str] = None
    created_at: str = field(default_factory=_utcnow_iso)
    # Denormalized from parent Video for GSI1
    published_at: Optional[str] = None

    def to_item(self) -> dict:
        """Serialize to DynamoDB item."""
        item = {
            "PK": f"VIDEO#{self.video_id}",
            "SK": f"MENTION#{self.id}",
            "entity_type": "StockMention",
            "id": self.id,
            "video_id": self.video_id,
            "ticker": self.ticker,
            "sentiment": self.sentiment,
            "created_at": self.created_at,
        }
        if self.ticker:
            item["GSI1PK"] = f"TICKER#{self.ticker}"
        if self.published_at:
            item["GSI1SK"] = self.published_at
        if self.price_at_mention is not None:
            item["price_at_mention"] = Decimal(str(self.price_at_mention))
        if self.confidence_score is not None:
            item["confidence_score"] = Decimal(str(self.confidence_score))
        if self.context_snippet:
            item["context_snippet"] = self.context_snippet
        return item

    @classmethod
    def from_item(cls, item: dict) -> "StockMention":
        """Deserialize from DynamoDB item."""
        price = item.get("price_at_mention")
        score = item.get("confidence_score")
        return cls(
            id=item["id"],
            video_id=item["video_id"],
            ticker=item["ticker"],
            sentiment=item["sentiment"],
            price_at_mention=float(price) if price is not None else None,
            confidence_score=float(score) if score is not None else None,
            context_snippet=item.get("context_snippet"),
            created_at=item["created_at"],
            published_at=item.get("GSI1SK"),
        )

    def to_response_dict(self, video: Optional["Video"] = None) -> dict:
        """Convert to dict compatible with StockMentionResponse Pydantic model."""
        result = {
            "id": self.id,
            "video_id": self.video_id,
            "ticker": self.ticker,
            "sentiment": self.sentiment,
            "price_at_mention": self.price_at_mention,
            "confidence_score": self.confidence_score,
            "context_snippet": self.context_snippet,
            "created_at": _parse_iso(self.created_at),
        }
        if video:
            result["video"] = video.to_response_dict()
        return result


@dataclass
class ProcessingLog:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    log_id: int = field(default_factory=_log_sequence_id)
    channel_id: str = ""
    log_level: str = "info"
    message: str = ""
    created_at: str = field(default_factory=_utcnow_iso)

    def to_item(self) -> dict:
        """Serialize to DynamoDB item."""
        return {
            "PK": f"CHANNEL#{self.channel_id}",
            "SK": f"LOG#{self.created_at}#{self.id[:8]}",
            "entity_type": "ProcessingLog",
            "id": self.id,
            "log_id": self.log_id,
            "channel_id": self.channel_id,
            "log_level": self.log_level,
            "message": self.message,
            "created_at": self.created_at,
        }

    @classmethod
    def from_item(cls, item: dict) -> "ProcessingLog":
        """Deserialize from DynamoDB item."""
        return cls(
            id=item["id"],
            log_id=int(item.get("log_id", 0)),
            channel_id=item["channel_id"],
            log_level=item["log_level"],
            message=item["message"],
            created_at=item["created_at"],
        )

    def to_response_dict(self) -> dict:
        """Convert to dict compatible with ProcessingLogResponse Pydantic model."""
        return {
            "id": self.log_id,  # API expects int
            "channel_id": self.channel_id,
            "log_level": self.log_level,
            "message": self.message,
            "created_at": _parse_iso(self.created_at),
        }
