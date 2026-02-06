import pytest
from datetime import date
from sqlalchemy.exc import IntegrityError

from app.db.models import Channel, Video, Stock, StockMention, ProcessingLog


class TestChannelModel:
    def test_create_channel(self, db_session):
        """Test creating a channel."""
        channel = Channel(
            youtube_channel_id="UC123456789",
            name="Test Channel",
            url="https://www.youtube.com/@TestChannel",
        )
        db_session.add(channel)
        db_session.commit()

        assert channel.id is not None
        assert channel.status == "pending"
        assert channel.video_count == 0
        assert channel.time_range_months == 12
        assert channel.created_at is not None

    def test_channel_unique_youtube_id(self, db_session):
        """Test that youtube_channel_id must be unique."""
        channel1 = Channel(
            youtube_channel_id="UC123",
            name="Channel 1",
            url="https://youtube.com/@channel1",
        )
        channel2 = Channel(
            youtube_channel_id="UC123",
            name="Channel 2",
            url="https://youtube.com/@channel2",
        )
        db_session.add(channel1)
        db_session.commit()

        db_session.add(channel2)
        with pytest.raises(IntegrityError):
            db_session.commit()


class TestVideoModel:
    def test_create_video(self, db_session):
        """Test creating a video linked to a channel."""
        channel = Channel(
            youtube_channel_id="UC123",
            name="Test Channel",
            url="https://youtube.com/@test",
        )
        db_session.add(channel)
        db_session.commit()

        video = Video(
            channel_id=channel.id,
            youtube_video_id="abc123",
            title="Test Video",
            url="https://youtube.com/watch?v=abc123",
            published_at=date(2024, 1, 15),
        )
        db_session.add(video)
        db_session.commit()

        assert video.id is not None
        assert video.channel_id == channel.id
        assert video.transcript_status == "pending"
        assert video.analysis_status == "pending"

    def test_video_channel_relationship(self, db_session):
        """Test video-channel relationship."""
        channel = Channel(
            youtube_channel_id="UC123",
            name="Test Channel",
            url="https://youtube.com/@test",
        )
        db_session.add(channel)
        db_session.commit()

        video = Video(
            channel_id=channel.id,
            youtube_video_id="abc123",
            title="Test Video",
            url="https://youtube.com/watch?v=abc123",
            published_at=date(2024, 1, 15),
        )
        db_session.add(video)
        db_session.commit()

        # Access relationship
        assert video.channel.name == "Test Channel"
        assert len(channel.videos) == 1
        assert channel.videos[0].title == "Test Video"

    def test_video_cascade_delete(self, db_session):
        """Test that videos are deleted when channel is deleted."""
        channel = Channel(
            youtube_channel_id="UC123",
            name="Test Channel",
            url="https://youtube.com/@test",
        )
        db_session.add(channel)
        db_session.commit()

        video = Video(
            channel_id=channel.id,
            youtube_video_id="abc123",
            title="Test Video",
            url="https://youtube.com/watch?v=abc123",
            published_at=date(2024, 1, 15),
        )
        db_session.add(video)
        db_session.commit()
        video_id = video.id

        db_session.delete(channel)
        db_session.commit()

        assert db_session.get(Video, video_id) is None


class TestStockModel:
    def test_create_stock(self, db_session):
        """Test creating a stock."""
        stock = Stock(
            ticker="AAPL",
            name="Apple Inc.",
            exchange="NASDAQ",
        )
        db_session.add(stock)
        db_session.commit()

        assert stock.ticker == "AAPL"
        assert stock.exchange == "NASDAQ"


class TestStockMentionModel:
    def test_create_stock_mention(self, db_session):
        """Test creating a stock mention."""
        # Create prerequisites
        channel = Channel(
            youtube_channel_id="UC123",
            name="Test Channel",
            url="https://youtube.com/@test",
        )
        db_session.add(channel)
        db_session.commit()

        video = Video(
            channel_id=channel.id,
            youtube_video_id="abc123",
            title="Test Video",
            url="https://youtube.com/watch?v=abc123",
            published_at=date(2024, 1, 15),
        )
        db_session.add(video)

        stock = Stock(ticker="AAPL", name="Apple Inc.", exchange="NASDAQ")
        db_session.add(stock)
        db_session.commit()

        mention = StockMention(
            video_id=video.id,
            ticker="AAPL",
            sentiment="buy",
            price_at_mention=185.50,
            context_snippet="I think Apple is a great buy right now",
        )
        db_session.add(mention)
        db_session.commit()

        assert mention.id is not None
        assert mention.sentiment == "buy"
        assert float(mention.price_at_mention) == 185.50

    def test_stock_mention_relationships(self, db_session):
        """Test stock mention relationships."""
        channel = Channel(
            youtube_channel_id="UC123",
            name="Test Channel",
            url="https://youtube.com/@test",
        )
        db_session.add(channel)
        db_session.commit()

        video = Video(
            channel_id=channel.id,
            youtube_video_id="abc123",
            title="Test Video",
            url="https://youtube.com/watch?v=abc123",
            published_at=date(2024, 1, 15),
        )
        db_session.add(video)

        stock = Stock(ticker="AAPL", name="Apple Inc.", exchange="NASDAQ")
        db_session.add(stock)
        db_session.commit()

        mention = StockMention(
            video_id=video.id,
            ticker="AAPL",
            sentiment="buy",
        )
        db_session.add(mention)
        db_session.commit()

        # Test relationships
        assert mention.video.title == "Test Video"
        assert mention.stock.name == "Apple Inc."
        assert len(video.stock_mentions) == 1
        assert len(stock.mentions) == 1


class TestProcessingLogModel:
    def test_create_processing_log(self, db_session):
        """Test creating a processing log."""
        channel = Channel(
            youtube_channel_id="UC123",
            name="Test Channel",
            url="https://youtube.com/@test",
        )
        db_session.add(channel)
        db_session.commit()

        log = ProcessingLog(
            channel_id=channel.id,
            log_level="info",
            message="Processing started",
        )
        db_session.add(log)
        db_session.commit()

        assert log.id is not None
        assert log.log_level == "info"
        assert log.created_at is not None

    def test_processing_log_cascade_delete(self, db_session):
        """Test that logs are deleted when channel is deleted."""
        channel = Channel(
            youtube_channel_id="UC123",
            name="Test Channel",
            url="https://youtube.com/@test",
        )
        db_session.add(channel)
        db_session.commit()

        log = ProcessingLog(
            channel_id=channel.id,
            log_level="info",
            message="Test log",
        )
        db_session.add(log)
        db_session.commit()
        log_id = log.id

        db_session.delete(channel)
        db_session.commit()

        assert db_session.get(ProcessingLog, log_id) is None
