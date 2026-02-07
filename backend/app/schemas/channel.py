from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field, field_validator
import re


class ChannelCreate(BaseModel):
    url: str = Field(..., description="YouTube channel URL")
    time_range_months: int = Field(default=12, ge=1, le=36)

    @field_validator("url")
    @classmethod
    def validate_youtube_url(cls, v: str) -> str:
        patterns = [
            r"youtube\.com/@[\w-]+",
            r"youtube\.com/channel/[\w-]+",
            r"youtube\.com/c/[\w-]+",
            r"youtube\.com/user/[\w-]+",
        ]
        if not any(re.search(pattern, v) for pattern in patterns):
            raise ValueError("Invalid YouTube channel URL")
        return v


class ChannelResponse(BaseModel):
    id: str
    youtube_channel_id: str
    name: str
    url: str
    thumbnail_url: Optional[str] = None
    status: str
    video_count: int
    processed_video_count: int
    time_range_months: int
    created_at: datetime
    updated_at: datetime



class ChannelListResponse(BaseModel):
    items: List[ChannelResponse]
    total: int
    page: int
    per_page: int


class ProcessingLogResponse(BaseModel):
    id: int
    channel_id: str
    log_level: str
    message: str
    created_at: datetime


class LogsResponse(BaseModel):
    logs: List[ProcessingLogResponse]
