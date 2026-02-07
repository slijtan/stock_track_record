from decimal import Decimal

from app.db.dynamodb import get_table
from app.db.dynamodb_models import Channel, Video, Stock, StockMention, ProcessingLog


class TestChannelModel:
    def test_create_channel(self, dynamodb_tables):
        """Test creating a channel and round-tripping through DynamoDB."""
        table = get_table()
        channel = Channel(
            youtube_channel_id="UC123456789",
            name="Test Channel",
            url="https://www.youtube.com/@TestChannel",
        )
        table.put_item(Item=channel.to_item())

        # Read back
        response = table.get_item(
            Key={"PK": f"CHANNEL#{channel.id}", "SK": f"CHANNEL#{channel.id}"}
        )
        loaded = Channel.from_item(response["Item"])

        assert loaded.id == channel.id
        assert loaded.status == "pending"
        assert loaded.video_count == 0
        assert loaded.time_range_months == 12
        assert loaded.created_at is not None

    def test_channel_to_response_dict(self, dynamodb_tables):
        """Test channel to_response_dict conversion."""
        channel = Channel(
            youtube_channel_id="UC123",
            name="Test Channel",
            url="https://youtube.com/@test",
        )
        resp = channel.to_response_dict()

        assert resp["id"] == channel.id
        assert resp["name"] == "Test Channel"
        assert resp["status"] == "pending"
        assert resp["video_count"] == 0


class TestVideoModel:
    def test_create_video(self, dynamodb_tables):
        """Test creating a video linked to a channel."""
        table = get_table()

        channel = Channel(
            youtube_channel_id="UC123",
            name="Test Channel",
            url="https://youtube.com/@test",
        )
        table.put_item(Item=channel.to_item())

        video = Video(
            channel_id=channel.id,
            youtube_video_id="abc123",
            title="Test Video",
            url="https://youtube.com/watch?v=abc123",
            published_at="2024-01-15",
        )
        table.put_item(Item=video.to_item())

        # Read back
        response = table.get_item(
            Key={"PK": f"CHANNEL#{channel.id}", "SK": f"VIDEO#{video.id}"}
        )
        loaded = Video.from_item(response["Item"])

        assert loaded.id == video.id
        assert loaded.channel_id == channel.id
        assert loaded.transcript_status == "pending"
        assert loaded.analysis_status == "pending"


class TestStockModel:
    def test_create_stock(self, dynamodb_tables):
        """Test creating a stock."""
        stocks_table = get_table("-Stocks")
        stock = Stock(
            ticker="AAPL",
            name="Apple Inc.",
            exchange="NASDAQ",
        )
        stocks_table.put_item(Item=stock.to_item())

        # Read back
        response = stocks_table.get_item(Key={"ticker": "AAPL"})
        loaded = Stock.from_item(response["Item"])

        assert loaded.ticker == "AAPL"
        assert loaded.exchange == "NASDAQ"
        assert loaded.name == "Apple Inc."


class TestStockMentionModel:
    def test_create_stock_mention(self, dynamodb_tables):
        """Test creating a stock mention."""
        table = get_table()

        video = Video(
            channel_id="test-channel-id",
            youtube_video_id="abc123",
            title="Test Video",
            url="https://youtube.com/watch?v=abc123",
            published_at="2024-01-15",
        )
        table.put_item(Item=video.to_item())

        mention = StockMention(
            video_id=video.id,
            ticker="AAPL",
            sentiment="buy",
            price_at_mention=185.50,
            context_snippet="I think Apple is a great buy right now",
            published_at="2024-01-15",
        )
        table.put_item(Item=mention.to_item())

        # Read back
        response = table.get_item(
            Key={"PK": f"VIDEO#{video.id}", "SK": f"MENTION#{mention.id}"}
        )
        loaded = StockMention.from_item(response["Item"])

        assert loaded.id == mention.id
        assert loaded.sentiment == "buy"
        assert loaded.price_at_mention == 185.50
        assert loaded.context_snippet == "I think Apple is a great buy right now"


class TestProcessingLogModel:
    def test_create_processing_log(self, dynamodb_tables):
        """Test creating a processing log."""
        table = get_table()

        channel = Channel(
            youtube_channel_id="UC123",
            name="Test Channel",
            url="https://youtube.com/@test",
        )
        table.put_item(Item=channel.to_item())

        log = ProcessingLog(
            channel_id=channel.id,
            log_level="info",
            message="Processing started",
        )
        table.put_item(Item=log.to_item())

        # Read back via SK prefix query
        from boto3.dynamodb.conditions import Key
        response = table.query(
            KeyConditionExpression=Key("PK").eq(f"CHANNEL#{channel.id}")
            & Key("SK").begins_with("LOG#"),
        )

        assert len(response["Items"]) == 1
        loaded = ProcessingLog.from_item(response["Items"][0])
        assert loaded.log_level == "info"
        assert loaded.message == "Processing started"
        assert loaded.log_id > 0
