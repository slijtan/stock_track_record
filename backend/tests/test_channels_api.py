from app.db.dynamodb import get_table
from app.db.dynamodb_models import Channel, Video, Stock, StockMention


class TestCreateChannel:
    def test_create_channel_success(self, client):
        """Test creating a channel with valid URL."""
        response = client.post(
            "/api/channels",
            json={
                "url": "https://www.youtube.com/@TestChannel",
                "time_range_months": 12,
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "TestChannel"
        assert data["status"] == "pending"
        assert data["time_range_months"] == 12

    def test_create_channel_invalid_url(self, client):
        """Test creating a channel with invalid URL."""
        response = client.post(
            "/api/channels",
            json={
                "url": "https://www.google.com/search",
                "time_range_months": 12,
            },
        )
        assert response.status_code == 422  # Validation error

    def test_create_channel_duplicate(self, client):
        """Test creating a duplicate channel."""
        # Create first channel
        client.post(
            "/api/channels",
            json={"url": "https://www.youtube.com/@TestChannel"},
        )
        # Try to create duplicate
        response = client.post(
            "/api/channels",
            json={"url": "https://www.youtube.com/@TestChannel"},
        )
        assert response.status_code == 400
        assert "already exists" in response.json()["detail"]


class TestListChannels:
    def test_list_channels_empty(self, client):
        """Test listing channels when none exist."""
        response = client.get("/api/channels")
        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 0

    def test_list_channels_with_data(self, client):
        """Test listing channels with data."""
        # Create channels
        client.post(
            "/api/channels",
            json={"url": "https://www.youtube.com/@Channel1"},
        )
        client.post(
            "/api/channels",
            json={"url": "https://www.youtube.com/@Channel2"},
        )

        response = client.get("/api/channels")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 2
        assert data["total"] == 2

    def test_list_channels_pagination(self, client):
        """Test channel list pagination."""
        # Create 5 channels
        for i in range(5):
            client.post(
                "/api/channels",
                json={"url": f"https://www.youtube.com/@Channel{i}"},
            )

        response = client.get("/api/channels?page=1&per_page=2")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 2
        assert data["total"] == 5
        assert data["page"] == 1
        assert data["per_page"] == 2


class TestGetChannel:
    def test_get_channel_success(self, client):
        """Test getting a channel by ID."""
        # Create channel
        create_response = client.post(
            "/api/channels",
            json={"url": "https://www.youtube.com/@TestChannel"},
        )
        channel_id = create_response.json()["id"]

        response = client.get(f"/api/channels/{channel_id}")
        assert response.status_code == 200
        assert response.json()["id"] == channel_id

    def test_get_channel_not_found(self, client):
        """Test getting a non-existent channel."""
        response = client.get("/api/channels/non-existent-id")
        assert response.status_code == 404


class TestDeleteChannel:
    def test_delete_channel_success(self, client):
        """Test deleting a channel."""
        # Create channel
        create_response = client.post(
            "/api/channels",
            json={"url": "https://www.youtube.com/@TestChannel"},
        )
        channel_id = create_response.json()["id"]

        response = client.delete(f"/api/channels/{channel_id}")
        assert response.status_code == 204

        # Verify deleted
        response = client.get(f"/api/channels/{channel_id}")
        assert response.status_code == 404

    def test_delete_channel_not_found(self, client):
        """Test deleting a non-existent channel."""
        response = client.delete("/api/channels/non-existent-id")
        assert response.status_code == 404


class TestChannelLogs:
    def test_get_channel_logs(self, client):
        """Test getting channel logs."""
        # Create channel
        create_response = client.post(
            "/api/channels",
            json={"url": "https://www.youtube.com/@TestChannel"},
        )
        channel_id = create_response.json()["id"]

        response = client.get(f"/api/channels/{channel_id}/logs")
        assert response.status_code == 200
        assert "logs" in response.json()


class TestChannelStocks:
    def test_get_channel_stocks_empty(self, client):
        """Test getting stocks for a channel with no data."""
        create_response = client.post(
            "/api/channels",
            json={"url": "https://www.youtube.com/@TestChannel"},
        )
        channel_id = create_response.json()["id"]

        response = client.get(f"/api/channels/{channel_id}/stocks")
        assert response.status_code == 200
        data = response.json()
        assert data["channel_id"] == channel_id
        assert data["stocks"] == []

    def test_get_channel_stocks_with_data(self, client):
        """Test getting stocks for a channel with stock mentions."""
        table = get_table()
        stocks_table = get_table("-Stocks")

        # Create channel directly in DynamoDB
        channel = Channel(
            youtube_channel_id="UC123",
            name="Test Channel",
            url="https://youtube.com/@test",
            status="completed",
        )
        table.put_item(Item=channel.to_item())

        video = Video(
            channel_id=channel.id,
            youtube_video_id="abc123",
            title="Test Video",
            url="https://youtube.com/watch?v=abc123",
            published_at="2024-01-15",
            analysis_status="completed",
        )
        table.put_item(Item=video.to_item())

        stock = Stock(ticker="AAPL", name="Apple Inc.", exchange="NASDAQ")
        stocks_table.put_item(Item=stock.to_item())

        mention = StockMention(
            video_id=video.id,
            ticker="AAPL",
            sentiment="buy",
            price_at_mention=185.50,
            published_at="2024-01-15",
        )
        table.put_item(Item=mention.to_item())

        response = client.get(f"/api/channels/{channel.id}/stocks")
        assert response.status_code == 200
        data = response.json()
        assert len(data["stocks"]) == 1
        assert data["stocks"][0]["ticker"] == "AAPL"
        assert data["stocks"][0]["buy_count"] == 1


class TestChannelTimeline:
    def test_get_channel_timeline(self, client):
        """Test getting timeline for a channel."""
        table = get_table()

        channel = Channel(
            youtube_channel_id="UC123",
            name="Test Channel",
            url="https://youtube.com/@test",
            status="completed",
        )
        table.put_item(Item=channel.to_item())

        video = Video(
            channel_id=channel.id,
            youtube_video_id="abc123",
            title="Test Video",
            url="https://youtube.com/watch?v=abc123",
            published_at="2024-01-15",
            analysis_status="completed",
        )
        table.put_item(Item=video.to_item())

        mention = StockMention(
            video_id=video.id,
            ticker="AAPL",
            sentiment="buy",
            published_at="2024-01-15",
        )
        table.put_item(Item=mention.to_item())

        response = client.get(f"/api/channels/{channel.id}/timeline")
        assert response.status_code == 200
        data = response.json()
        assert len(data["timeline"]) == 1
        assert data["timeline"][0]["video"]["title"] == "Test Video"
        assert len(data["timeline"][0]["mentions"]) == 1


class TestStockDrilldown:
    def test_get_stock_drilldown(self, client):
        """Test getting stock drilldown."""
        table = get_table()

        channel = Channel(
            youtube_channel_id="UC123",
            name="Test Channel",
            url="https://youtube.com/@test",
            status="completed",
        )
        table.put_item(Item=channel.to_item())

        video = Video(
            channel_id=channel.id,
            youtube_video_id="abc123",
            title="Test Video",
            url="https://youtube.com/watch?v=abc123",
            published_at="2024-01-15",
            analysis_status="completed",
        )
        table.put_item(Item=video.to_item())

        mention = StockMention(
            video_id=video.id,
            ticker="AAPL",
            sentiment="buy",
            price_at_mention=185.50,
            published_at="2024-01-15",
        )
        table.put_item(Item=mention.to_item())

        response = client.get(f"/api/channels/{channel.id}/stocks/AAPL")
        assert response.status_code == 200
        data = response.json()
        assert data["ticker"] == "AAPL"
        assert len(data["mentions"]) == 1
        assert data["mentions"][0]["sentiment"] == "buy"
