import uuid
from datetime import datetime
from sqlalchemy import (
    Column,
    String,
    Integer,
    Enum,
    Text,
    DECIMAL,
    Date,
    DateTime,
    ForeignKey,
    Index,
)
from sqlalchemy.orm import relationship

from app.db.database import Base


def generate_uuid():
    return str(uuid.uuid4())


class Channel(Base):
    __tablename__ = "channels"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    youtube_channel_id = Column(String(50), nullable=False, unique=True)
    name = Column(String(255), nullable=False)
    url = Column(String(500), nullable=False)
    thumbnail_url = Column(String(500), nullable=True)
    status = Column(
        Enum("pending", "processing", "completed", "failed", "cancelled", name="channel_status"),
        default="pending",
    )
    video_count = Column(Integer, default=0)
    processed_video_count = Column(Integer, default=0)
    time_range_months = Column(Integer, default=12)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    videos = relationship("Video", back_populates="channel", cascade="all, delete-orphan")
    processing_logs = relationship(
        "ProcessingLog", back_populates="channel", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("idx_channel_status", "status"),
        Index("idx_channel_created_at", "created_at"),
    )


class Video(Base):
    __tablename__ = "videos"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    channel_id = Column(String(36), ForeignKey("channels.id", ondelete="CASCADE"), nullable=False)
    youtube_video_id = Column(String(20), nullable=False, unique=True)
    title = Column(String(500), nullable=False)
    url = Column(String(500), nullable=False)
    published_at = Column(Date, nullable=False)
    transcript_status = Column(
        Enum("pending", "fetched", "failed", name="transcript_status"),
        default="pending",
    )
    analysis_status = Column(
        Enum("pending", "completed", "failed", name="analysis_status"),
        default="pending",
    )
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    channel = relationship("Channel", back_populates="videos")
    stock_mentions = relationship(
        "StockMention", back_populates="video", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("idx_video_channel_id", "channel_id"),
        Index("idx_video_published_at", "published_at"),
    )


class Stock(Base):
    __tablename__ = "stocks"

    ticker = Column(String(10), primary_key=True)
    name = Column(String(255), nullable=True)
    exchange = Column(
        Enum("NYSE", "NASDAQ", name="stock_exchange"),
        nullable=False,
    )
    last_price = Column(DECIMAL(12, 4), nullable=True)
    price_updated_at = Column(DateTime, nullable=True)

    # Relationships
    mentions = relationship("StockMention", back_populates="stock")

    __table_args__ = (Index("idx_stock_exchange", "exchange"),)


class StockMention(Base):
    __tablename__ = "stock_mentions"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    video_id = Column(String(36), ForeignKey("videos.id", ondelete="CASCADE"), nullable=False)
    ticker = Column(String(10), ForeignKey("stocks.ticker"), nullable=False)
    sentiment = Column(
        Enum("buy", "hold", "sell", "mentioned", name="sentiment_type"),
        nullable=False,
    )
    price_at_mention = Column(DECIMAL(12, 4), nullable=True)
    confidence_score = Column(DECIMAL(3, 2), nullable=True)
    context_snippet = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    video = relationship("Video", back_populates="stock_mentions")
    stock = relationship("Stock", back_populates="mentions")

    __table_args__ = (
        Index("idx_mention_video_id", "video_id"),
        Index("idx_mention_ticker", "ticker"),
        Index("unique_video_ticker", "video_id", "ticker", unique=True),
    )


class ProcessingLog(Base):
    __tablename__ = "processing_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    channel_id = Column(String(36), ForeignKey("channels.id", ondelete="CASCADE"), nullable=False)
    log_level = Column(
        Enum("info", "warning", "error", name="log_level"),
        default="info",
    )
    message = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    channel = relationship("Channel", back_populates="processing_logs")

    __table_args__ = (Index("idx_log_channel_created", "channel_id", "created_at"),)
