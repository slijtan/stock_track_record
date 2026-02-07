# Plan 0001: Migrate Local Database from MySQL to DynamoDB

## Spec Reference
`codev/specs/0001-mysql-to-dynamodb-local.md`

## Implementation Strategy

This migration replaces the entire database layer. The strategy is **bottom-up**: build the new DynamoDB foundation first, then rewire services, then update routers, then tests. Each phase produces testable output.

**7 phases, executed sequentially:**

1. Infrastructure (Docker + config + DynamoDB client)
2. Data models (dataclasses replacing SQLAlchemy models)
3. DynamoDB helpers (query utilities, batch operations)
4. Service layer rewrite (channel_service, processing_service, stock_price_service)
5. Router layer rewrite (channels, stocks)
6. Test rewrite
7. Cleanup (remove MySQL artifacts)

---

## Phase 1: Infrastructure

**Goal**: DynamoDB Local running in Docker, boto3 client configured, tables can be created.

### Step 1.1: Replace docker-compose.yml

Replace MySQL container with DynamoDB Local:

```yaml
services:
  dynamodb-local:
    image: amazon/dynamodb-local:latest
    container_name: stock-track-dynamodb
    ports:
      - "8000:8000"
    command: "-jar DynamoDBLocal.jar -sharedDb -dbPath /home/dynamodblocal/data"
    volumes:
      - stock_track_dynamodb_data:/home/dynamodblocal/data
    healthcheck:
      test: ["CMD-SHELL", "wget -q -O /dev/null http://localhost:8000 || exit 1"]
      interval: 10s
      timeout: 5s
      retries: 5

volumes:
  stock_track_dynamodb_data:
```

### Step 1.2: Update backend/app/config.py

Replace `database_url` with DynamoDB settings:

```python
class Settings(BaseSettings):
    # Application
    app_name: str = "Stock Track Record"
    debug: bool = False

    # Database (DynamoDB)
    dynamodb_endpoint: str = "http://localhost:8000"
    dynamodb_table_prefix: str = "StockTrackRecord"
    dynamodb_region: str = "us-east-1"

    # External APIs (unchanged)
    youtube_api_key: str = ""
    openai_api_key: str = ""
    gemini_api_key: str = ""
    finnhub_api_key: str = ""
    alpha_vantage_api_key: str = ""

    # Frontend (unchanged)
    frontend_url: str = "http://localhost:5173"

    # AWS (unchanged)
    aws_region: str = "us-east-1"
    sqs_queue_url: str = ""
    is_lambda: bool = False

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
    }
```

### Step 1.3: Create backend/app/db/dynamodb.py

DynamoDB client factory + table creation + helpers:

```python
import boto3
from boto3.dynamodb.conditions import Key, Attr
from app.config import get_settings

_resource = None
_client = None

def get_dynamodb_resource():
    """Shared boto3 DynamoDB resource (singleton, thread-safe for operations)."""
    global _resource
    if _resource is None:
        settings = get_settings()
        kwargs = {"region_name": settings.dynamodb_region}
        if settings.dynamodb_endpoint:
            kwargs["endpoint_url"] = settings.dynamodb_endpoint
            # DynamoDB Local ignores credentials but boto3 requires them
            kwargs["aws_access_key_id"] = "local"
            kwargs["aws_secret_access_key"] = "local"
        _resource = boto3.resource("dynamodb", **kwargs)
    return _resource

def get_dynamodb_client():
    """Shared boto3 DynamoDB client (singleton, thread-safe for operations)."""
    global _client
    if _client is None:
        settings = get_settings()
        kwargs = {"region_name": settings.dynamodb_region}
        if settings.dynamodb_endpoint:
            kwargs["endpoint_url"] = settings.dynamodb_endpoint
            kwargs["aws_access_key_id"] = "local"
            kwargs["aws_secret_access_key"] = "local"
        _client = boto3.client("dynamodb", **kwargs)
    return _client

def get_table(suffix: str = ""):
    """Get a DynamoDB Table object by suffix. '' = main table, '-Stocks' = stocks table."""
    settings = get_settings()
    resource = get_dynamodb_resource()
    return resource.Table(settings.dynamodb_table_prefix + suffix)

def reset_clients():
    """Reset cached clients (for testing)."""
    global _resource, _client
    _resource = None
    _client = None

def create_tables(resource=None, prefix=None):
    """Create all DynamoDB tables. Used by create_tables.py script and tests."""
    # Implementation: create main table with 3 GSIs + stocks table
    # See spec for exact schema
    ...

def delete_tables(resource=None, prefix=None):
    """Delete all DynamoDB tables. Used by test cleanup."""
    ...
```

The `create_tables` function must create:

**Main table** (`{prefix}`):
- PK (S) + SK (S)
- GSI1: GSI1PK (S) + GSI1SK (S), projection ALL
- GSI2: GSI2PK (S), projection ALL
- GSI3: GSI3PK (S), projection KEYS_ONLY
- BillingMode: PAY_PER_REQUEST

**Stocks table** (`{prefix}-Stocks`):
- ticker (S)
- BillingMode: PAY_PER_REQUEST

### Step 1.4: Create backend/scripts/create_tables.py

Standalone script to create tables (replaces `alembic upgrade head`):

```python
#!/usr/bin/env python
"""Create DynamoDB tables for Stock Track Record."""
import sys
sys.path.insert(0, ".")
from app.db.dynamodb import get_dynamodb_resource, create_tables
from app.config import get_settings

if __name__ == "__main__":
    settings = get_settings()
    print(f"Creating tables with prefix '{settings.dynamodb_table_prefix}' at {settings.dynamodb_endpoint}")
    resource = get_dynamodb_resource()
    create_tables(resource, prefix=settings.dynamodb_table_prefix)
    print("Tables created successfully.")
```

### Step 1.5: Update backend/requirements.txt

Remove MySQL dependencies:
```
# Remove these lines:
# sqlalchemy==2.0.25
# pymysql==1.1.0
# alembic==1.13.1

# boto3 already present, no additions needed
```

### Step 1.6: Update backend/.env.example

Add DynamoDB config, remove DATABASE_URL:
```
# DynamoDB
DYNAMODB_ENDPOINT=http://localhost:8000
DYNAMODB_TABLE_PREFIX=StockTrackRecord
DYNAMODB_REGION=us-east-1
AWS_ACCESS_KEY_ID=local
AWS_SECRET_ACCESS_KEY=local
```

### Phase 1 verification
```bash
docker compose up -d
cd backend && python scripts/create_tables.py
# Should print "Tables created successfully"
# Verify: aws dynamodb list-tables --endpoint-url http://localhost:8000
```

---

## Phase 2: Data Models

**Goal**: Dataclass models with DynamoDB serialization, replacing SQLAlchemy ORM models.

### Step 2.1: Create backend/app/db/dynamodb_models.py

Five dataclasses matching the spec's table design:

```python
from dataclasses import dataclass, field, asdict
from datetime import datetime, date
from typing import Optional
from decimal import Decimal
import uuid

def _utcnow_iso() -> str:
    return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

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

@dataclass
class Stock:
    ticker: str = ""
    name: Optional[str] = None
    exchange: str = "NYSE"
    last_price: Optional[float] = None
    price_updated_at: Optional[str] = None

    def to_item(self) -> dict:
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
    # Denormalized fields for GSI1 (query mentions by ticker)
    published_at: Optional[str] = None  # From the parent video

    def to_item(self) -> dict:
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
        # GSI1 for ticker-based queries
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

@dataclass
class ProcessingLog:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    channel_id: str = ""
    log_level: str = "info"
    message: str = ""
    created_at: str = field(default_factory=_utcnow_iso)

    def to_item(self) -> dict:
        return {
            "PK": f"CHANNEL#{self.channel_id}",
            "SK": f"LOG#{self.created_at}#{self.id[:8]}",
            "entity_type": "ProcessingLog",
            "id": self.id,
            "channel_id": self.channel_id,
            "log_level": self.log_level,
            "message": self.message,
            "created_at": self.created_at,
        }

    @classmethod
    def from_item(cls, item: dict) -> "ProcessingLog":
        return cls(
            id=item["id"],
            channel_id=item["channel_id"],
            log_level=item["log_level"],
            message=item["message"],
            created_at=item["created_at"],
        )
```

### Key design decisions:
- `published_at` on Video is stored as ISO date string `YYYY-MM-DD` (not datetime) matching the existing `Date` column
- `price_at_mention` and `last_price` use `Decimal` for DynamoDB (DynamoDB doesn't support float), converted to/from float at the model boundary
- `StockMention.published_at` is denormalized from the parent Video for GSI1SK
- `ProcessingLog` SK uses `LOG#{created_at}#{id[:8]}` for chronological ordering with collision avoidance
- `entity_type` attribute added to every item for debugging/filtering

### Phase 2 verification
- Unit test: create each dataclass, call `to_item()`, verify keys, call `from_item()`, verify round-trip

---

## Phase 3: DynamoDB Helpers

**Goal**: Reusable query utilities that handle pagination, batch operations, and retries.

### Step 3.1: Add helpers to backend/app/db/dynamodb.py

```python
import time
from boto3.dynamodb.conditions import Key, Attr

def query_all_pages(table, **kwargs) -> list:
    """Query DynamoDB and follow all LastEvaluatedKey pages. Handles 1MB limit."""
    items = []
    response = table.query(**kwargs)
    items.extend(response.get("Items", []))
    while "LastEvaluatedKey" in response:
        kwargs["ExclusiveStartKey"] = response["LastEvaluatedKey"]
        response = table.query(**kwargs)
        items.extend(response.get("Items", []))
    return items

def query_count(table, **kwargs) -> int:
    """Query DynamoDB with Select=COUNT, following all pages."""
    kwargs["Select"] = "COUNT"
    total = 0
    response = table.query(**kwargs)
    total += response.get("Count", 0)
    while "LastEvaluatedKey" in response:
        kwargs["ExclusiveStartKey"] = response["LastEvaluatedKey"]
        response = table.query(**kwargs)
        total += response.get("Count", 0)
    return total

def batch_delete_with_retry(table, items: list, max_retries: int = 5):
    """Delete items in batches of 25 with exponential backoff retry for UnprocessedItems."""
    table_name = table.table_name
    resource = table.meta.client.meta.service_model  # Get resource from table
    # Use the resource's batch_writer which handles batching and retries
    # OR manual implementation:
    dynamodb = get_dynamodb_resource()
    keys = [{"PK": item["PK"], "SK": item["SK"]} for item in items]

    # Split into batches of 25
    for i in range(0, len(keys), 25):
        batch = keys[i:i+25]
        request_items = {
            table_name: [{"DeleteRequest": {"Key": k}} for k in batch]
        }
        retries = 0
        while request_items and retries < max_retries:
            response = dynamodb.meta.client.batch_write_item(RequestItems=request_items)
            request_items = response.get("UnprocessedItems", {})
            if request_items:
                retries += 1
                time.sleep(2 ** retries * 0.1)  # Exponential backoff: 0.2s, 0.4s, 0.8s...
        if request_items:
            raise RuntimeError(f"Failed to delete {len(request_items)} items after {max_retries} retries")
```

**Alternative**: Use `table.batch_writer()` context manager which handles batching and retries automatically. Prefer this for simplicity:

```python
def batch_delete_items(table, items: list):
    """Delete items using batch_writer (handles batching + retries automatically)."""
    with table.batch_writer() as batch:
        for item in items:
            batch.delete_item(Key={"PK": item["PK"], "SK": item["SK"]})
```

The `batch_writer()` context manager handles:
- Batching into groups of 25
- Automatic retry of UnprocessedItems with backoff
- Flush on context exit

**Use `batch_writer()` as primary approach.** Only fall back to manual `batch_write_item` if we need finer control over retry behavior.

### Phase 3 verification
- Integration test against DynamoDB Local: insert items, `query_all_pages`, verify results
- Integration test: insert >25 items, `batch_delete_items`, verify all deleted

---

## Phase 4: Service Layer Rewrite

**Goal**: Rewrite channel_service.py, processing_service.py, and stock_price_service.py to use DynamoDB instead of SQLAlchemy.

**Critical change**: Service functions no longer accept a `db: Session` parameter. They call `get_table()` directly. This removes the SQLAlchemy session dependency from the entire codebase.

### Step 4.1: Rewrite backend/app/services/channel_service.py

Function-by-function mapping:

| Function | Current (SQLAlchemy) | New (DynamoDB) |
|----------|---------------------|----------------|
| `extract_channel_identifier(url)` | No DB, pure logic | **Unchanged** |
| `create_channel(db, url, time_range)` | `db.add()` + `db.commit()` | `table.put_item(Item=channel.to_item())` + check GSI2 for duplicates |
| `get_channel(db, channel_id)` | `db.query().filter().first()` | `table.get_item(Key={"PK": f"CHANNEL#{id}", "SK": f"CHANNEL#{id}"})` |
| `list_channels(db, page, per_page)` | `db.query().order_by().offset().limit()` | Query GSI1, scan-and-skip pagination |
| `delete_channel(db, channel_id)` | `db.delete()` (cascade) | Multi-query + `batch_writer` delete |
| `get_channel_logs(db, channel_id, since)` | `db.query().filter()` | `Query PK=CHANNEL#{id}, SK begins_with LOG#` |
| `add_processing_log(db, channel_id, msg, level)` | `db.add()` + `db.commit()` | `table.put_item(Item=log.to_item())` |
| `get_channel_stocks(db, channel_id)` | Complex aggregation across videos + mentions | Same logic but with DynamoDB queries |
| `get_channel_timeline(db, channel_id)` | Query videos + mentions per video | Same pattern |
| `get_stock_drilldown(db, channel_id, ticker)` | Filter by video_ids + ticker | Use FilterExpression |

**Signature changes**: All functions drop the `db: Session` parameter. Example:

```python
# Before:
def create_channel(db: Session, url: str, time_range_months: int = 12) -> Channel:

# After:
def create_channel(url: str, time_range_months: int = 12) -> Channel:
```

**Duplicate detection** for `create_channel`:
```python
# Check for existing channel by youtube_channel_id via GSI2
table = get_table()
response = table.query(
    IndexName="GSI2-index",
    KeyConditionExpression=Key("GSI2PK").eq(f"YT#{youtube_channel_id}"),
    Limit=1,
)
if response.get("Items"):
    raise ValueError("Channel already exists")
```

**Pagination for `list_channels`**:
```python
def list_channels(page: int = 1, per_page: int = 20) -> tuple[list[Channel], int]:
    table = get_table()

    # Get total count
    total = query_count(table,
        IndexName="GSI1-index",
        KeyConditionExpression=Key("GSI1PK").eq("CHANNELS"),
    )

    # Query page
    query_kwargs = {
        "IndexName": "GSI1-index",
        "KeyConditionExpression": Key("GSI1PK").eq("CHANNELS"),
        "ScanIndexForward": False,  # newest first
        "Limit": per_page,
    }

    # Skip forward for page > 1
    items = []
    pages_to_skip = page - 1
    response = table.query(**query_kwargs)

    if pages_to_skip == 0:
        items = response.get("Items", [])
    else:
        # Skip pages
        for _ in range(pages_to_skip):
            if "LastEvaluatedKey" not in response:
                return [], total  # Past last page
            query_kwargs["ExclusiveStartKey"] = response["LastEvaluatedKey"]
            response = table.query(**query_kwargs)
        items = response.get("Items", [])

    channels = [Channel.from_item(item) for item in items]
    return channels, total
```

**Cascade delete for `delete_channel`**:
```python
def delete_channel(channel_id: str) -> bool:
    table = get_table()

    # Step 1: Get channel item to verify it exists
    response = table.get_item(Key={"PK": f"CHANNEL#{channel_id}", "SK": f"CHANNEL#{channel_id}"})
    if "Item" not in response:
        return False

    # Step 2: Query all items under CHANNEL#{channel_id} partition
    # Gets: channel record, all videos, all logs
    channel_items = query_all_pages(table,
        KeyConditionExpression=Key("PK").eq(f"CHANNEL#{channel_id}"),
    )

    # Step 3: For each video, query its mentions
    all_items = list(channel_items)
    for item in channel_items:
        if item["SK"].startswith("VIDEO#"):
            video_id = item["id"]
            mentions = query_all_pages(table,
                KeyConditionExpression=Key("PK").eq(f"VIDEO#{video_id}") & Key("SK").begins_with("MENTION#"),
            )
            all_items.extend(mentions)

    # Step 4: Batch delete all items
    batch_delete_items(table, all_items)
    return True
```

### Step 4.2: Rewrite backend/app/services/processing_service.py

**Key changes**:
- Remove `from app.db.database import SessionLocal` - no longer needed
- Remove `db: Session` parameter from `process_channel` and `process_video_threadsafe`
- Each function calls `get_table()` directly
- Thread tasks no longer create `SessionLocal()` - just call service functions
- `add_log` function calls `get_table().put_item()` directly

**Function mapping**:

| Function | Key change |
|----------|-----------|
| `add_log(db, channel_id, msg, level)` | Drop `db` param. `get_table().put_item(Item=log.to_item())` |
| `process_channel(db, channel_id)` | Drop `db` param. `get_table().get_item(...)` for channel, `UpdateItem` for status changes |
| `process_video_threadsafe(db, ...)` | Drop `db` param. Use `get_table()` directly. No `SessionLocal()` needed |
| `backfill_historical_prices(db, channel_id)` | Drop `db` param. Query mentions, update with `UpdateItem` |
| `get_yahoo_historical_price(...)` | **Unchanged** (no DB) |

**Thread safety simplification**:
```python
# Before (SQLAlchemy):
def process_video_task(video_data):
    thread_db = SessionLocal()
    try:
        result = process_video_threadsafe(thread_db, channel_id, video_data, gemini_api_key)
        return result
    finally:
        thread_db.close()

# After (DynamoDB):
def process_video_task(video_data):
    return process_video_threadsafe(channel_id, video_data, gemini_api_key)
    # No session management needed - get_table() is thread-safe
```

**Channel status updates** use `UpdateItem` instead of ORM attribute mutation:
```python
table = get_table()
table.update_item(
    Key={"PK": f"CHANNEL#{channel_id}", "SK": f"CHANNEL#{channel_id}"},
    UpdateExpression="SET #status = :status, updated_at = :now",
    ExpressionAttributeNames={"#status": "status"},
    ExpressionAttributeValues={":status": "processing", ":now": _utcnow_iso()},
)
```

**Video existence check** uses GSI3:
```python
# Check if video already processed
response = table.query(
    IndexName="GSI3-index",
    KeyConditionExpression=Key("GSI3PK").eq(f"YTVID#{video_id}"),
    Limit=1,
)
if response.get("Items"):
    return {"status": "skipped"}
```

**Stock upsert** on the stocks table:
```python
stocks_table = get_table("-Stocks")
stocks_table.put_item(Item=stock.to_item())
```

**StockMention creation**:
```python
mention = StockMention(
    video_id=video.id,
    ticker=ticker,
    sentiment=sentiment,
    context_snippet=context,
    published_at=video.published_at,  # Denormalized for GSI1
)
table.put_item(Item=mention.to_item())
```

### Step 4.3: Update backend/app/services/stock_price_service.py

Only one function uses DB: `get_current_price(db, ticker)`.

**Change**: Drop `db` parameter, query stocks table directly:

```python
def get_current_price(ticker: str) -> dict:
    ticker = ticker.upper()

    # Check memory cache (unchanged)
    if ticker in _price_cache:
        ...

    # Check DynamoDB for recent price
    stocks_table = get_table("-Stocks")
    response = stocks_table.get_item(Key={"ticker": ticker})
    db_stock = Stock.from_item(response["Item"]) if "Item" in response else None

    if db_stock and db_stock.last_price and db_stock.price_updated_at:
        age = datetime.utcnow() - datetime.fromisoformat(db_stock.price_updated_at.replace("Z", "+00:00")).replace(tzinfo=None)
        if age < timedelta(hours=1):
            # Cache and return (same logic as before)
            ...

    # Fetch from Finnhub (unchanged)
    ...

    # Update DynamoDB
    if db_stock:
        stocks_table.update_item(
            Key={"ticker": ticker},
            UpdateExpression="SET last_price = :price, price_updated_at = :now",
            ExpressionAttributeValues={":price": Decimal(str(price)), ":now": _utcnow_iso()},
        )
```

### Phase 4 verification
- Start DynamoDB Local, create tables
- Run `create_channel` / `get_channel` / `list_channels` / `delete_channel` manually via Python REPL
- Verify cascade delete removes all related items

---

## Phase 5: Router Layer Rewrite

**Goal**: Update FastAPI routers to call the new session-less service functions.

### Step 5.1: Rewrite backend/app/routers/channels.py

**Key changes**:
- Remove all `db: Session = Depends(get_db)` parameters
- Remove `from app.db.database import get_db, SessionLocal`
- Service function calls drop the `db` argument
- Background task functions no longer create `SessionLocal()`

Example endpoint changes:

```python
# Before:
@router.post("/channels", response_model=ChannelResponse, status_code=201)
async def create_channel(
    channel: ChannelCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    result = channel_service.create_channel(db, channel.url, channel.time_range_months)

# After:
@router.post("/channels", response_model=ChannelResponse, status_code=201)
async def create_channel(
    channel: ChannelCreate,
    background_tasks: BackgroundTasks,
):
    result = channel_service.create_channel(channel.url, channel.time_range_months)
```

**Background task simplification**:
```python
# Before:
def run_channel_processing(channel_id: str):
    db = SessionLocal()
    try:
        process_channel(db, channel_id)
    except Exception as e:
        print(f"Processing error: {e}")
    finally:
        db.close()

# After:
def run_channel_processing(channel_id: str):
    try:
        process_channel(channel_id)
    except Exception as e:
        print(f"Processing error: {e}")
```

**Response model compatibility**: The Pydantic schemas use `model_config = {"from_attributes": True}` to read from SQLAlchemy ORM objects. With dataclasses, this still works because Pydantic's `from_attributes` also reads dataclass attributes. However, we need to handle:

1. `ChannelResponse.created_at` expects `datetime`, but our dataclass stores ISO string → Add a `@field_validator` or update the schema to accept strings and parse them
2. `ProcessingLogResponse.id` expects `int`, but our logs use UUID strings → Change to `str`
3. `VideoResponse.published_at` expects `date`, but our dataclass stores ISO string → Parse in validator

**Approach**: Update Pydantic schemas to handle both cases OR convert in the router layer. **Prefer converting in the router** to keep changes minimal:

```python
# In channels.py, when returning a ChannelResponse:
channel = channel_service.get_channel(channel_id)
return ChannelResponse(
    id=channel.id,
    youtube_channel_id=channel.youtube_channel_id,
    name=channel.name,
    url=channel.url,
    thumbnail_url=channel.thumbnail_url,
    status=channel.status,
    video_count=channel.video_count,
    processed_video_count=channel.processed_video_count,
    time_range_months=channel.time_range_months,
    created_at=datetime.fromisoformat(channel.created_at.replace("Z", "+00:00")),
    updated_at=datetime.fromisoformat(channel.updated_at.replace("Z", "+00:00")),
)
```

**Centralized approach**: Add a `to_response_dict()` method on each dataclass that returns a dict with datetime-converted fields, compatible with Pydantic model constructors. This keeps conversion logic in one place per entity:

```python
# On Channel dataclass:
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

# Helper at module level:
def _parse_iso(iso_str: str) -> datetime:
    """Parse ISO 8601 string to datetime."""
    return datetime.fromisoformat(iso_str.replace("Z", "+00:00"))

def _parse_date(date_str: str) -> date:
    """Parse ISO date string to date."""
    return date.fromisoformat(date_str)
```

Each dataclass gets `to_response_dict()`. Router code becomes:
```python
channel = channel_service.get_channel(channel_id)
return ChannelResponse(**channel.to_response_dict())
```

This is centralized (one conversion per entity type), testable, and avoids scattered datetime parsing in routers.

### Step 5.2: Update backend/app/routers/stocks.py

```python
# Before:
@router.get("/stocks/{ticker}/price", response_model=StockPriceResponse)
async def get_stock_price(ticker: str, db: Session = Depends(get_db)):
    price_data = stock_price_service.get_current_price(db, ticker.upper())

# After:
@router.get("/stocks/{ticker}/price", response_model=StockPriceResponse)
async def get_stock_price(ticker: str):
    price_data = stock_price_service.get_current_price(ticker.upper())
```

### Step 5.3: Update backend/app/schemas/channel.py

**ProcessingLogResponse.id must remain `int`** to preserve the API contract (Spec Goal #3).

Since DynamoDB doesn't have auto-increment, generate a monotonically increasing integer from the timestamp:

```python
import time

def _log_sequence_id() -> int:
    """Generate a monotonically increasing integer ID from timestamp microseconds."""
    return int(time.time() * 1_000_000)  # Microsecond precision
```

Update the `ProcessingLog` dataclass to store both the UUID (for DynamoDB key) and a numeric `log_id` (for the API):

```python
@dataclass
class ProcessingLog:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    log_id: int = field(default_factory=_log_sequence_id)  # API-facing integer ID
    channel_id: str = ""
    log_level: str = "info"
    message: str = ""
    created_at: str = field(default_factory=_utcnow_iso)
```

The `ProcessingLogResponse` schema stays unchanged:
```python
class ProcessingLogResponse(BaseModel):
    id: int  # Stays int - mapped from log_id
    channel_id: str
    log_level: str
    message: str
    created_at: datetime
```

When building the response, map `log_id` → `id`:
```python
ProcessingLogResponse(
    id=log.log_id,
    channel_id=log.channel_id,
    log_level=log.log_level,
    message=log.message,
    created_at=datetime.fromisoformat(log.created_at.replace("Z", "+00:00")),
)
```

This preserves the API contract exactly. The `log_id` is unique to microsecond precision, which is sufficient since processing logs are not created concurrently within the same channel.

### Step 5.4: Update backend/app/main.py

Remove SQLAlchemy imports. Add table creation on startup (aligning with spec's "File Changes" section which says `main.py` should add DynamoDB table creation on startup):

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup - ensure DynamoDB tables exist
    from app.db.dynamodb import ensure_tables_exist
    ensure_tables_exist()

    if not settings.is_lambda:
        from app.services.background_tasks import start_background_runner
        start_background_runner()
    yield
    # Shutdown - nothing to clean up
```

The `ensure_tables_exist()` function in `dynamodb.py` will call `create_tables()` but catch `ResourceInUseException` for tables that already exist (idempotent). This means:
- `docker compose up -d && uvicorn app.main:app` just works (no separate script needed)
- `scripts/create_tables.py` still exists as a standalone utility for CI/debugging

### Phase 5 verification
```bash
docker compose up -d
python scripts/create_tables.py
uvicorn app.main:app --reload
# Test endpoints manually:
curl -X POST http://localhost:8000/api/channels -H 'Content-Type: application/json' -d '{"url":"https://www.youtube.com/@TestChannel"}'
curl http://localhost:8000/api/channels
curl http://localhost:8000/health
```

---

## Phase 6: Test Rewrite

**Goal**: All tests pass against DynamoDB Local.

### Step 6.1: Rewrite backend/tests/conftest.py

```python
import pytest
import uuid
import boto3
from fastapi.testclient import TestClient

from app.main import app
from app.db.dynamodb import create_tables, delete_tables, reset_clients, get_table
from app.config import get_settings


@pytest.fixture(scope="session")
def dynamodb_resource():
    """Shared DynamoDB resource for all tests."""
    return boto3.resource(
        "dynamodb",
        endpoint_url="http://localhost:8000",
        region_name="us-east-1",
        aws_access_key_id="test",
        aws_secret_access_key="test",
    )


@pytest.fixture(scope="function")
def dynamodb_tables(dynamodb_resource, monkeypatch):
    """Create fresh DynamoDB tables for each test with unique prefix."""
    test_prefix = f"test-{uuid.uuid4().hex[:8]}"

    # Patch settings to use test prefix
    monkeypatch.setenv("DYNAMODB_TABLE_PREFIX", test_prefix)
    monkeypatch.setenv("DYNAMODB_ENDPOINT", "http://localhost:8000")
    monkeypatch.setenv("DYNAMODB_REGION", "us-east-1")

    # Reset cached clients so they pick up new settings
    reset_clients()
    get_settings.cache_clear()

    create_tables(dynamodb_resource, prefix=test_prefix)
    yield test_prefix

    # Cleanup
    delete_tables(dynamodb_resource, prefix=test_prefix)
    reset_clients()
    get_settings.cache_clear()


@pytest.fixture(scope="function")
def client(dynamodb_tables):
    """Create a test client with DynamoDB tables."""
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(scope="function")
def client_no_db():
    """Create a test client without database (for health check tests)."""
    with TestClient(app) as test_client:
        yield test_client
```

### Step 6.2: Rewrite backend/tests/test_models.py

Replace SQLAlchemy model tests with dataclass + DynamoDB round-trip tests:

- Test `Channel`: create, `to_item()`, put to DynamoDB, `get_item`, `from_item()`, verify fields
- Test `Video`: create under a channel, query by PK, verify
- Test `Stock`: put to stocks table, get, verify
- Test `StockMention`: create under a video, query by PK, verify
- Test `ProcessingLog`: create under a channel, query by PK + SK prefix, verify ordering
- Test cascade delete: create channel + video + mention + log, delete channel, verify all gone
- Test unique youtube_channel_id: attempt duplicate, verify service raises ValueError

### Step 6.3: Rewrite backend/tests/test_channels_api.py

Test structure stays the same (TestCreateChannel, TestListChannels, TestGetChannel, etc.) but:
- Replace `db_session` fixture with `dynamodb_tables` fixture (via `client` fixture)
- Replace direct SQLAlchemy model creation with service calls or direct DynamoDB puts
- Tests that create data directly in DB (e.g., `TestChannelStocks.test_get_channel_stocks_with_data`) use `get_table().put_item()` instead of `db_session.add()`

Example:
```python
class TestChannelStocks:
    def test_get_channel_stocks_with_data(self, client, dynamodb_tables):
        table = get_table()
        stocks_table = get_table("-Stocks")

        channel = Channel(youtube_channel_id="UC123", name="Test Channel",
                         url="https://youtube.com/@test", status="completed")
        table.put_item(Item=channel.to_item())

        video = Video(channel_id=channel.id, youtube_video_id="abc123",
                     title="Test Video", url="https://youtube.com/watch?v=abc123",
                     published_at="2024-01-15", analysis_status="completed")
        table.put_item(Item=video.to_item())

        stock = Stock(ticker="AAPL", name="Apple Inc.", exchange="NASDAQ")
        stocks_table.put_item(Item=stock.to_item())

        mention = StockMention(video_id=video.id, ticker="AAPL", sentiment="buy",
                              price_at_mention=185.50, published_at="2024-01-15")
        table.put_item(Item=mention.to_item())

        response = client.get(f"/api/channels/{channel.id}/stocks")
        assert response.status_code == 200
        data = response.json()
        assert len(data["stocks"]) == 1
        assert data["stocks"][0]["ticker"] == "AAPL"
```

### Step 6.4: Update backend/tests/test_services.py

`test_services.py` tests YouTube and OpenAI services which have no DB dependency. These tests should pass without changes, but verify imports don't pull in SQLAlchemy.

### Step 6.5: Update backend/tests/test_health.py

Should pass without changes since health check has no DB dependency.

### Phase 6 verification
```bash
docker compose up -d
python scripts/create_tables.py  # Create default tables (tests create their own)
cd backend && python -m pytest tests/ -v
```

---

## Phase 7: Cleanup

**Goal**: Remove all MySQL/SQLAlchemy artifacts.

### Step 7.1: Delete files

```
rm backend/app/db/database.py
rm backend/app/db/models.py
rm -rf backend/alembic/
rm -f backend/alembic.ini
```

### Step 7.2: Verify no remaining references

```bash
grep -r "sqlalchemy" backend/ --include="*.py"
grep -r "pymysql" backend/ --include="*.py"
grep -r "alembic" backend/ --include="*.py"
grep -r "database_url" backend/ --include="*.py"
grep -r "get_db" backend/ --include="*.py"
grep -r "SessionLocal" backend/ --include="*.py"
```

All should return empty.

### Step 7.3: Update backend/app/db/__init__.py

If it imports from `database.py` or `models.py`, update to import from new files.

### Step 7.4: Final verification

```bash
# Full test suite
cd backend && python -m pytest tests/ -v

# Start app and smoke test
uvicorn app.main:app --reload
curl http://localhost:8000/health
curl http://localhost:8000/api/channels
```

---

## Implementation Order Summary

| Phase | Files Created | Files Modified | Files Deleted | Estimated Size |
|-------|-------------|---------------|---------------|---------------|
| 1. Infrastructure | `dynamodb.py`, `create_tables.py` | `config.py`, `docker-compose.yml`, `requirements.txt`, `.env.example` | - | ~200 lines |
| 2. Data Models | `dynamodb_models.py` | - | - | ~250 lines |
| 3. DynamoDB Helpers | - | `dynamodb.py` (add helpers) | - | ~60 lines |
| 4. Service Layer | - | `channel_service.py`, `processing_service.py`, `stock_price_service.py` | - | ~500 lines |
| 5. Router Layer | - | `channels.py`, `stocks.py`, `main.py`, `schemas/channel.py` | - | ~300 lines |
| 6. Tests | - | `conftest.py`, `test_models.py`, `test_channels_api.py`, `test_services.py` | - | ~350 lines |
| 7. Cleanup | - | `__init__.py` | `database.py`, `models.py`, `alembic/`, `alembic.ini` | ~0 lines |
| **Total** | **3 new** | **~14 modified** | **~8 deleted** | **~1660 lines** |

## Acceptance Tests

After all phases complete, verify each acceptance criterion from the spec:

1. **All 13 endpoints identical** → Run full API test suite + manual curl tests
2. **MySQL replaced with DynamoDB Local** → `docker compose ps` shows `stock-track-dynamodb`, no MySQL
3. **Startup works** → `docker compose up -d && uvicorn app.main:app` succeeds (tables auto-created)
4. **SQLAlchemy removed** → `grep -r sqlalchemy backend/` returns nothing
5. **Tests pass** → `pytest tests/ -v` all green
6. **Background processing works** → Create channel via API, verify processing logs appear
7. **Cascade delete works** → Create channel with data, delete, verify all gone
8. **No frontend changes** → Frontend runs without modifications
9. **1MB pagination handled** → `query_all_pages` used everywhere
10. **Batch retry handled** → `batch_writer()` or `batch_delete_with_retry` used for all batch operations

---

## Consultation Log

### Round 1 (Codex + Gemini)
- **Codex**: REQUEST_CHANGES - ProcessingLogResponse.id API break, startup table creation mismatch, response conversion not centralized
- **Gemini**: APPROVE - Plan is detailed and sound

**Changes made**:
- Fixed ProcessingLogResponse.id: Keep as `int`, use microsecond-precision timestamp as `log_id` field on dataclass, map to `id` in response
- Added `ensure_tables_exist()` on app startup in `main.py` lifespan (aligns with spec, idempotent)
- Added centralized `to_response_dict()` methods on each dataclass for datetime conversion
- Updated acceptance test #3 to reflect startup auto-creation
