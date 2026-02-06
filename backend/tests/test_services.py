import pytest
from unittest.mock import patch, MagicMock

from app.services import youtube_service, openai_service


class TestYouTubeService:
    def test_extract_channel_info_handle(self):
        """Test extracting channel info from handle URL."""
        url = "https://www.youtube.com/@TestChannel"
        result = youtube_service.extract_channel_info_from_url(url)
        assert result["identifier"] == "TestChannel"
        assert result["type"] == "handle"

    def test_extract_channel_info_channel_id(self):
        """Test extracting channel info from channel ID URL."""
        url = "https://www.youtube.com/channel/UC1234567890"
        result = youtube_service.extract_channel_info_from_url(url)
        assert result["identifier"] == "UC1234567890"
        assert result["type"] == "channel_id"

    def test_extract_channel_info_custom(self):
        """Test extracting channel info from custom URL."""
        url = "https://www.youtube.com/c/CustomChannel"
        result = youtube_service.extract_channel_info_from_url(url)
        assert result["identifier"] == "CustomChannel"
        assert result["type"] == "custom"

    def test_extract_channel_info_user(self):
        """Test extracting channel info from user URL."""
        url = "https://www.youtube.com/user/OldStyleUser"
        result = youtube_service.extract_channel_info_from_url(url)
        assert result["identifier"] == "OldStyleUser"
        assert result["type"] == "user"

    def test_extract_channel_info_invalid(self):
        """Test extracting channel info from invalid URL."""
        with pytest.raises(ValueError):
            youtube_service.extract_channel_info_from_url("https://google.com")

    def test_extract_video_id(self):
        """Test extracting video ID from URL."""
        urls = [
            ("https://www.youtube.com/watch?v=abc123", "abc123"),
            ("https://youtu.be/xyz789", "xyz789"),
            ("https://www.youtube.com/embed/def456", "def456"),
        ]
        for url, expected_id in urls:
            assert youtube_service.extract_video_id(url) == expected_id

    def test_extract_video_id_invalid(self):
        """Test extracting video ID from invalid URL."""
        assert youtube_service.extract_video_id("https://google.com") is None


class TestOpenAIService:
    @patch('app.services.openai_service.OpenAI')
    def test_extract_stock_mentions_success(self, mock_openai_class):
        """Test extracting stock mentions with mocked OpenAI."""
        # Mock response
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = '{"stocks": [{"ticker": "AAPL", "sentiment": "buy", "context": "Apple is great"}]}'
        mock_client.chat.completions.create.return_value = mock_response

        # Transcript needs to be at least 50 chars
        result = openai_service.extract_stock_mentions(
            "test-api-key",
            "I think Apple stock is a great buy right now. AAPL has strong fundamentals. " * 2
        )

        assert len(result) == 1
        assert result[0]["ticker"] == "AAPL"
        assert result[0]["sentiment"] == "buy"

    @patch('app.services.openai_service.OpenAI')
    def test_extract_stock_mentions_no_stocks(self, mock_openai_class):
        """Test extracting stock mentions when no stocks found."""
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = '{"stocks": []}'
        mock_client.chat.completions.create.return_value = mock_response

        result = openai_service.extract_stock_mentions(
            "test-api-key",
            "This is a video about cooking recipes and delicious food. " * 2
        )

        assert len(result) == 0

    def test_extract_stock_mentions_empty_transcript(self):
        """Test with empty transcript."""
        result = openai_service.extract_stock_mentions("test-api-key", "")
        assert len(result) == 0

    def test_extract_stock_mentions_no_api_key(self):
        """Test without API key."""
        with pytest.raises(ValueError):
            openai_service.extract_stock_mentions("", "Some transcript")

    @patch('app.services.openai_service.OpenAI')
    def test_extract_stock_mentions_multiple(self, mock_openai_class):
        """Test extracting multiple stock mentions."""
        import json
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps({
            "stocks": [
                {"ticker": "AAPL", "sentiment": "buy", "context": "Apple buy"},
                {"ticker": "TSLA", "sentiment": "sell", "context": "Tesla sell"},
                {"ticker": "MSFT", "sentiment": "hold", "context": "Microsoft hold"},
                {"ticker": "GOOGL", "sentiment": "mentioned", "context": "Google mentioned"}
            ]
        })
        mock_client.chat.completions.create.return_value = mock_response

        result = openai_service.extract_stock_mentions(
            "test-api-key",
            "Discussing AAPL, TSLA, MSFT, and GOOGL. " * 10  # Make transcript longer
        )

        assert len(result) == 4
        sentiments = {r["ticker"]: r["sentiment"] for r in result}
        assert sentiments["AAPL"] == "buy"
        assert sentiments["TSLA"] == "sell"
        assert sentiments["MSFT"] == "hold"
        assert sentiments["GOOGL"] == "mentioned"

    def test_validate_stock_mentions(self):
        """Test validating stock mentions."""
        mentions = [
            {"ticker": "AAPL", "sentiment": "buy"},
            {"ticker": "INVALID", "sentiment": "buy"},
            {"ticker": "TSLA", "sentiment": "sell"},
        ]
        valid_tickers = ["AAPL", "TSLA", "MSFT"]

        result = openai_service.validate_stock_mentions(mentions, valid_tickers)

        assert len(result) == 2
        tickers = [r["ticker"] for r in result]
        assert "AAPL" in tickers
        assert "TSLA" in tickers
        assert "INVALID" not in tickers
