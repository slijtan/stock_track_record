from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # Application
    app_name: str = "Stock Track Record"
    debug: bool = False

    # Database
    database_url: str = "mysql+pymysql://root:root@localhost:3306/stock_track_record"

    # External APIs
    youtube_api_key: str = ""
    openai_api_key: str = ""
    gemini_api_key: str = ""
    finnhub_api_key: str = ""
    alpha_vantage_api_key: str = ""

    # Frontend
    frontend_url: str = "http://localhost:5173"

    # AWS (for Lambda deployment)
    aws_region: str = "us-east-1"
    sqs_queue_url: str = ""
    is_lambda: bool = False

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
    }


@lru_cache()
def get_settings() -> Settings:
    return Settings()
