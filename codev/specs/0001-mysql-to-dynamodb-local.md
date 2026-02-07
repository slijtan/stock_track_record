# Spec 0001: Migrate Local Database from MySQL to DynamoDB

## Status
Conceived

## Summary
Replace the SQLAlchemy/MySQL database layer with a boto3-based DynamoDB implementation for local development. The local environment will use [DynamoDB Local](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/DynamoDBLocal.html) running in Docker, replacing the current MySQL 8.0 container.

This is **Phase 1 of 2**. Phase 2 (Spec 0002) will update the AWS Lambda deployment to use cloud DynamoDB instead of Aurora Serverless.

## Motivation
- **Cost reduction**: Aurora Serverless has minimum costs even when idle; DynamoDB on-demand pricing scales to zero
- **Operational simplicity**: DynamoDB is fully managed with no connection pooling, patching, or scaling configuration
- **Consistency**: Using DynamoDB both locally and in production eliminates MySQL/Aurora drift
- **Better fit for the data model**: The app's access patterns (get-by-ID, query-by-channel, query-by-ticker) map naturally to DynamoDB's key-value and query model
- **No migrations needed**: DynamoDB is schemaless; Alembic/migrations can be removed entirely

## Goals
1. Replace all SQLAlchemy ORM operations with boto3 DynamoDB operations
2. Replace the MySQL Docker container with DynamoDB Local in docker-compose.yml
<!-- REVIEW(@architect): make sure to use mounted volume so data persists locally -->
3. Maintain identical API behavior (all 13 endpoints return the same response shapes)
4. Remove SQLAlchemy, PyMySQL, and Alembic dependencies
5. Update tests to use DynamoDB Local instead of SQLite in-memory
6. Keep the codebase simple - no ORM abstraction layer, just direct boto3 calls

## Non-Goals
- Updating the AWS Lambda deployment (that's Spec 0002)
- Changing any frontend code or API contracts
- Adding new features or endpoints
- Data migration tooling (the app has no persistent production data yet)

## Current Architecture

### Database Stack
- **ORM**: SQLAlchemy 2.0.25 with declarative models
- **Driver**: PyMySQL 1.1.0
- **Migrations**: Alembic 1.13.1
- **Local DB**: MySQL 8.0 in Docker (port 3307)
- **Production DB**: Aurora Serverless v2 (MySQL 8.0 compatible)
- **Session management**: FastAPI dependency injection via `get_db()` yielding SQLAlchemy sessions

### Tables (5)
| Table | PK | Notable Columns | Relationships |
|-------|-----|-----------------|---------------|
| channels | id (UUID) | youtube_channel_id (unique), status (enum), video_count, processed_video_count | -> videos, processing_logs |
| videos | id (UUID) | channel_id (FK), youtube_video_id (unique), published_at, transcript_status, analysis_status | -> stock_mentions |
| stocks | ticker (string PK) | name, exchange (enum), last_price, price_updated_at | -> stock_mentions |
| stock_mentions | id (UUID) | video_id (FK), ticker (FK), sentiment (enum), price_at_mention, confidence_score, context_snippet | - |
| processing_logs | id (auto-increment) | channel_id (FK), log_level (enum), message, created_at | - |

### Access Patterns (from routers/channels.py and services/)
1. **Get channel by ID** - `channels` table, single item
2. **List channels (paginated)** - `channels` table, scan with count + offset/limit
3. **Get channel by youtube_channel_id** - `channels` table, unique lookup
4. **Delete channel (cascade)** - delete channel + all videos + all mentions + all logs
5. **Get videos by channel_id** - `videos` table, filter by channel_id
6. **Get video by youtube_video_id** - `videos` table, unique lookup
7. **Get stock mentions by video_id(s)** - `stock_mentions` table, filter by video_id, IN query
8. **Get stock mentions by video_id + ticker** - `stock_mentions` table, compound filter
9. **Get stock by ticker** - `stocks` table, single item by PK
10. **Get processing logs by channel_id** - `processing_logs` table, filter by channel_id, optional since timestamp
11. **Update channel status/counts** - `channels` table, attribute updates
12. **Update stock prices** - `stocks` table, update last_price + price_updated_at
13. **Update mention prices** - `stock_mentions` table, update price_at_mention
14. **Count mentions missing prices** - `stock_mentions` table, filter by video_ids + price_at_mention is None

## Technical Implementation

### DynamoDB Table Design

Use a **main single-table** plus **2 auxiliary tables** (2 tables total: main + stocks). All entities that require relational queries live in the main table using composite keys. Stocks are a simple lookup table.

#### Table 1: `{prefix}` (Main Table)

**Table name**: `{dynamodb_table_prefix}` (default: `StockTrackRecord`)

Primary key:
- `PK` (String) - Partition key
- `SK` (String) - Sort key

Billing: On-demand (PAY_PER_REQUEST)

| Entity | PK | SK | Attributes |
|--------|-----|-----|-----------|
| Channel | `CHANNEL#{id}` | `CHANNEL#{id}` | youtube_channel_id, name, url, thumbnail_url, status, video_count, processed_video_count, time_range_months, created_at, updated_at, GSI1PK, GSI1SK, GSI2PK |
| Video | `CHANNEL#{channel_id}` | `VIDEO#{id}` | youtube_video_id, title, url, published_at, transcript_status, analysis_status, created_at, GSI3PK |
| StockMention | `VIDEO#{video_id}` | `MENTION#{id}` | ticker, sentiment, price_at_mention, confidence_score, context_snippet, created_at, GSI1PK, GSI1SK |
| ProcessingLog | `CHANNEL#{channel_id}` | `LOG#{created_at_iso}#{uuid_suffix}` | log_level, message |

**Note on ProcessingLog SK**: Use `LOG#{ISO-8601-timestamp}#{first-8-chars-of-uuid}` for sort key. ISO 8601 UTC strings (e.g., `2025-01-15T08:30:00.000Z`) sort lexicographically. The UUID suffix prevents collisions for logs written at the same millisecond. No separate counter table needed.

**GSI-1**: `GSI1-index`
- Key: `GSI1PK` (String), `GSI1SK` (String)
- Projection: **ALL** (all attributes projected)

| Entity | GSI1PK | GSI1SK | Purpose |
|--------|--------|--------|---------|
| Channel | `CHANNELS` | `{created_at_iso}` | List all channels sorted by created_at (for pagination) |
| StockMention | `TICKER#{ticker}` | `{published_at_iso}` | Query mentions by ticker across videos |

**GSI-2**: `GSI2-index`
- Key: `GSI2PK` (String)
- SK: None (partition-key-only GSI)
- Projection: **ALL**

| Entity | GSI2PK | Purpose |
|--------|--------|---------|
| Channel | `YT#{youtube_channel_id}` | Unique lookup by YouTube channel ID |

**GSI-3**: `GSI3-index`
- Key: `GSI3PK` (String)
- SK: None (partition-key-only GSI)
- Projection: **KEYS_ONLY** (only returns PK/SK, used to find the item then GetItem on base table)

| Entity | GSI3PK | Purpose |
|--------|--------|---------|
| Video | `YTVID#{youtube_video_id}` | Unique lookup by YouTube video ID |

#### Table 2: `{prefix}-Stocks` (Reference Table)

**Table name**: `{dynamodb_table_prefix}-Stocks` (default: `StockTrackRecord-Stocks`)

Primary key:
- `ticker` (String) - Partition key

Billing: On-demand (PAY_PER_REQUEST)

| Attributes | Type |
|-----------|------|
| ticker | String |
| name | String |
| exchange | String |
| last_price | Number (Decimal) |
| price_updated_at | String (ISO 8601) |

This is a simple key-value table. Stocks are referenced by ticker and don't need relational queries.

#### Table Naming Convention

All table names are derived from `dynamodb_table_prefix` (config setting):
- Main table: `{prefix}` (e.g., `StockTrackRecord`)
- Stocks table: `{prefix}-Stocks` (e.g., `StockTrackRecord-Stocks`)
- Test tables: `{prefix}-test` and `{prefix}-test-Stocks` (for test isolation)

### Timestamp Format

All timestamps are stored as **ISO 8601 UTC strings** with zero-padded components for correct lexicographic sorting:
- Format: `YYYY-MM-DDTHH:MM:SS.fffZ` (e.g., `2025-01-15T08:30:00.000Z`)
- Always UTC (suffix `Z`)
- This ensures GSI1SK sorting works correctly for both channel listing and mention-by-ticker queries

### Access Pattern Mapping

| # | Access Pattern | DynamoDB Operation |
|---|---------------|-------------------|
| 1 | Get channel by ID | `GetItem PK=CHANNEL#{id}, SK=CHANNEL#{id}` |
| 2 | List channels (paginated) | `Query GSI1 GSI1PK=CHANNELS, ScanIndexForward=False, Limit=per_page` with `LastEvaluatedKey` cursor |
| 3 | Get channel by youtube_channel_id | `Query GSI2 GSI2PK=YT#{youtube_channel_id}` |
| 4 | Delete channel (cascade) | See "Cascade Delete" section below |
| 5 | Get videos by channel_id | `Query PK=CHANNEL#{channel_id}, SK begins_with VIDEO#` |
| 6 | Get video by youtube_video_id | `Query GSI3 GSI3PK=YTVID#{youtube_video_id}` → returns PK/SK → `GetItem` on base table |
| 7 | Get mentions by video_id(s) | For each video_id: `Query PK=VIDEO#{video_id}, SK begins_with MENTION#` |
| 8 | Get mentions by video_id + ticker | `Query PK=VIDEO#{video_id}, SK begins_with MENTION#, FilterExpression: ticker = :ticker` |
| 9 | Get stock by ticker | `GetItem {prefix}-Stocks ticker={ticker}` |
| 10 | Get logs by channel_id | `Query PK=CHANNEL#{channel_id}, SK begins_with LOG#, ScanIndexForward=True` (optionally: `SK > LOG#{since_timestamp}`) |
| 11 | Update channel | `UpdateItem PK=CHANNEL#{id}, SK=CHANNEL#{id}` with update expression |
| 12 | Update stock prices | `UpdateItem {prefix}-Stocks ticker={ticker}` |
| 13 | Update mention prices | `UpdateItem PK=VIDEO#{video_id}, SK=MENTION#{id}` |
| 14 | Count mentions missing prices | For each video_id: `Query PK=VIDEO#{video_id}, SK begins_with MENTION#, FilterExpression: attribute_not_exists(price_at_mention), Select=COUNT` |

**Note on pattern #14**: This uses `FilterExpression` server-side (not app-layer filtering) with `Select=COUNT` to avoid transferring items. For a channel with ~100 videos and ~5 mentions per video, this is ~100 queries returning only counts. Acceptable for the expected data scale (< 500 mentions per channel).

### Pagination

DynamoDB does not support offset-based pagination. The current API uses `page`/`per_page` parameters with SQL `OFFSET`/`LIMIT`.

**Approach**: Keep the existing `page`/`per_page` API contract:
- Query GSI1 with `GSI1PK=CHANNELS`, `ScanIndexForward=False` (newest first), `Limit=per_page`
- For `page > 1`: Execute repeated queries using `LastEvaluatedKey` to skip forward to the desired page
- **Ordering**: Channels are ordered by `created_at` descending (newest first), matching the current SQL `ORDER BY created_at DESC`
- **Consistency**: GSI queries are eventually consistent. This is acceptable since:
  - Channel creation is infrequent (user-initiated)
  - A newly created channel appearing on the next page load (milliseconds later) is fine
- **Total count**: Execute a separate `Select=COUNT` query on GSI1 with `GSI1PK=CHANNELS` to get total count for the pagination response
- **Scale caveat**: The scan-and-skip approach reads O(page * per_page) items. This is fine for < 100 channels. If channel counts grow significantly, switch to cursor-based pagination in the API

### File Changes

#### Files to Create
| File | Purpose |
|------|---------|
| `backend/app/db/dynamodb.py` | DynamoDB client/resource factory, `get_table()` helper, table creation |
| `backend/app/db/dynamodb_models.py` | Dataclasses for Channel, Video, Stock, StockMention, ProcessingLog with serialization helpers |
| `backend/scripts/create_tables.py` | Script to create DynamoDB tables (replaces `alembic upgrade head`) |

#### Files to Modify
| File | Changes |
|------|---------|
| `backend/app/config.py` | Replace `database_url` with `dynamodb_endpoint`, `dynamodb_table_prefix`, `dynamodb_region` |
| `backend/app/services/channel_service.py` | Rewrite all functions to use boto3 DynamoDB queries instead of SQLAlchemy |
| `backend/app/services/processing_service.py` | Rewrite DB operations to use boto3 (keep business logic unchanged) |
| `backend/app/routers/channels.py` | Remove `get_db` dependency, call service functions directly (no session passing). Remove `SessionLocal` usage in background tasks |
| `backend/app/routers/stocks.py` | Update to use DynamoDB stocks table |
| `backend/app/main.py` | Remove SQLAlchemy engine startup, add DynamoDB table creation on startup |
| `backend/requirements.txt` | Remove `sqlalchemy`, `pymysql`, `alembic`. `boto3` already present |
| `docker-compose.yml` | Replace MySQL container with DynamoDB Local container |
| `backend/tests/conftest.py` | Replace SQLite setup with DynamoDB Local test setup |
| `backend/tests/test_models.py` | Rewrite for DynamoDB data structures |
| `backend/tests/test_channels_api.py` | Update to work with DynamoDB test setup |
| `backend/tests/test_services.py` | Update to work with DynamoDB test setup |

#### Files to Delete
| File | Reason |
|------|--------|
| `backend/app/db/database.py` | Replaced by `dynamodb.py` |
| `backend/app/db/models.py` | Replaced by `dynamodb_models.py` |
| `backend/alembic/` (entire directory) | No migrations needed with DynamoDB |
| `backend/alembic.ini` | No longer needed |

### DynamoDB Local Docker Setup

Replace the MySQL container in `docker-compose.yml`:

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

**Note**: DynamoDB Local image is based on Amazon Linux and may not include `curl`. Use `wget` for healthcheck instead.

### Configuration Changes

```python
class Settings(BaseSettings):
    # Database (DynamoDB)
    dynamodb_endpoint: str = "http://localhost:8000"  # DynamoDB Local; empty string = use AWS default
    dynamodb_table_prefix: str = "StockTrackRecord"
    dynamodb_region: str = "us-east-1"

    # Remove: database_url
```

When `dynamodb_endpoint` is set (local dev), boto3 uses it. In production (Phase 2), set `dynamodb_endpoint=""` so boto3 uses IAM credentials and the default regional endpoint.

### Credential Handling

- **Local development**: DynamoDB Local ignores credentials entirely. Set dummy values `AWS_ACCESS_KEY_ID=local` and `AWS_SECRET_ACCESS_KEY=local` in `.env` to prevent boto3 from looking for real credentials
- **Production (Phase 2)**: Use IAM role attached to Lambda; no credentials in env vars
- **`.env.example`**: Update to include dummy AWS credentials and DynamoDB config

### DynamoDB Client Setup

```python
# backend/app/db/dynamodb.py
import boto3
from app.config import get_settings

_resource = None
_client = None

def get_dynamodb_resource():
    """Get shared boto3 DynamoDB resource (thread-safe for operations)."""
    global _resource
    if _resource is None:
        settings = get_settings()
        kwargs = {"region_name": settings.dynamodb_region}
        if settings.dynamodb_endpoint:
            kwargs["endpoint_url"] = settings.dynamodb_endpoint
        _resource = boto3.resource("dynamodb", **kwargs)
    return _resource

def get_dynamodb_client():
    """Get shared boto3 DynamoDB client (thread-safe for operations)."""
    global _client
    if _client is None:
        settings = get_settings()
        kwargs = {"region_name": settings.dynamodb_region}
        if settings.dynamodb_endpoint:
            kwargs["endpoint_url"] = settings.dynamodb_endpoint
        _client = boto3.client("dynamodb", **kwargs)
    return _client

def get_table(table_suffix: str = ""):
    """Get a DynamoDB Table object. Thread-safe: Table objects use the shared resource's connection pool."""
    settings = get_settings()
    resource = get_dynamodb_resource()
    table_name = settings.dynamodb_table_prefix + table_suffix
    return resource.Table(table_name)
```

**Thread safety note**: boto3 `client` and `resource` objects are thread-safe for making API calls. `Table` objects obtained from a `resource` share the underlying connection pool and are safe to use across threads. Each thread should call `get_table()` to get its own `Table` reference (which is cheap - no network call).

### Data Model (Dataclasses)

Replace SQLAlchemy models with simple dataclasses for type safety:

```python
# backend/app/db/dynamodb_models.py
from dataclasses import dataclass, field
from datetime import datetime, date
from typing import Optional
import uuid

def _utcnow_iso() -> str:
    """Return current UTC time as ISO 8601 string with Z suffix."""
    return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

@dataclass
class Channel:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    youtube_channel_id: str = ""
    name: str = ""
    url: str = ""
    thumbnail_url: Optional[str] = None
    status: str = "pending"  # pending, processing, completed, failed, cancelled
    video_count: int = 0
    processed_video_count: int = 0
    time_range_months: int = 12
    created_at: str = field(default_factory=_utcnow_iso)
    updated_at: str = field(default_factory=_utcnow_iso)

    def to_dynamo_item(self) -> dict:
        """Serialize to DynamoDB item dict with PK/SK and GSI keys."""
        item = {
            "PK": f"CHANNEL#{self.id}",
            "SK": f"CHANNEL#{self.id}",
            "GSI1PK": "CHANNELS",
            "GSI1SK": self.created_at,
            "GSI2PK": f"YT#{self.youtube_channel_id}",
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
    def from_dynamo_item(cls, item: dict) -> "Channel":
        """Deserialize from DynamoDB item dict."""
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
```

Similar dataclasses for Video, Stock, StockMention, ProcessingLog - each with `to_dynamo_item()` and `from_dynamo_item()` methods.

### Cascade Delete Implementation

DynamoDB has no cascade delete. Implement it explicitly:

```python
def delete_channel(channel_id: str):
    table = get_table()

    # Step 1: Query ALL items under the channel partition
    # This gets the channel itself, all videos, and all logs in one query
    channel_items = query_all_pages(
        table, KeyConditionExpression="PK = :pk",
        ExpressionAttributeValues={":pk": f"CHANNEL#{channel_id}"}
    )

    # Step 2: For each video, query its mentions
    all_items_to_delete = list(channel_items)
    for item in channel_items:
        if item["SK"].startswith("VIDEO#"):
            video_id = item["id"]
            mentions = query_all_pages(
                table, KeyConditionExpression="PK = :pk AND begins_with(SK, :sk)",
                ExpressionAttributeValues={
                    ":pk": f"VIDEO#{video_id}",
                    ":sk": "MENTION#"
                }
            )
            all_items_to_delete.extend(mentions)

    # Step 3: BatchWriteItem with retry for UnprocessedItems
    batch_delete_with_retry(table, all_items_to_delete)
```

**Step 1 optimization** (per Gemini review): Since channel, videos, and logs all share `PK=CHANNEL#{channel_id}`, a single query retrieves all three entity types. Only mentions need separate queries.

**Retry handling**: `BatchWriteItem` can return `UnprocessedItems` if throughput is exceeded. The `batch_delete_with_retry` helper must:
1. Split items into batches of 25 (DynamoDB limit)
2. Call `BatchWriteItem` for each batch
3. If `UnprocessedItems` is non-empty, exponential backoff and retry
4. Max 5 retries before raising an error

### Thread Safety for Processing

The current processing pipeline uses `ThreadPoolExecutor` with each thread getting its own SQLAlchemy `SessionLocal()`. With DynamoDB:

- Use a **shared boto3 resource** (module-level singleton via `get_dynamodb_resource()`)
- Each thread calls `get_table()` to get a `Table` reference (cheap, no network call)
- boto3 handles HTTP connection pooling internally via urllib3
- Remove the `SessionLocal()` pattern entirely from `processing_service.py`

### Enum Handling

MySQL `ENUM` columns enforced valid values at the DB level. With DynamoDB, enforce at the application level:
- Keep using Python string literals with validation in the dataclass/service layer
- The Pydantic schemas already validate enum values at the API boundary
- No change to API behavior

## Testing Strategy

### Unit Tests
- Replace SQLite in-memory with DynamoDB Local
- Test each service function's DynamoDB query logic
- Test cascade delete correctness (verify all related items deleted)
- Test pagination with cursor-based approach
- Test GSI lookups: `youtube_channel_id`, `youtube_video_id`
- Test `FilterExpression` queries (pattern #8 ticker filter, pattern #14 missing prices)
- Test BatchWriteItem retry logic

### Integration Tests
- Use DynamoDB Local container for integration tests
- Test all 13 API endpoints return identical response shapes
- Test background processing pipeline end-to-end

### Test Setup
```python
# conftest.py
import uuid

@pytest.fixture(scope="function")
def dynamodb_tables():
    """Create fresh DynamoDB tables for each test with unique prefix."""
    test_prefix = f"test-{uuid.uuid4().hex[:8]}"
    resource = boto3.resource("dynamodb", endpoint_url="http://localhost:8000",
                              region_name="us-east-1",
                              aws_access_key_id="test",
                              aws_secret_access_key="test")
    create_tables(resource, prefix=test_prefix)
    yield resource, test_prefix
    # Cleanup: delete test tables
    delete_tables(resource, prefix=test_prefix)
```

**Test isolation**: Each test gets a unique table prefix (e.g., `test-a1b2c3d4`) to avoid collisions when tests run in parallel.

## Risks and Mitigations

| Risk | Mitigation |
|------|-----------|
| DynamoDB query patterns are different from SQL | Spec defines exact PK/SK/GSI design for every access pattern |
| Pagination behavior changes (no offset) | Scan-and-skip approach preserves API contract for small datasets. Scale caveat documented |
| No cascade delete in DynamoDB | Explicit delete function with BatchWriteItem + retry for UnprocessedItems |
| IN queries (get mentions for multiple video_ids) | Loop over video_ids with individual queries; acceptable for <500 mentions per channel |
| No COUNT in DynamoDB | Use `Select='COUNT'` in Query to count server-side without transferring items |
| Thread safety differences | Shared boto3 resource with per-thread Table references; documented as safe |
| DynamoDB 1MB query limit | All query helpers must handle pagination via `LastEvaluatedKey` (`query_all_pages` helper) |
| Eventually consistent GSI reads | Acceptable for all access patterns (channel list, unique lookups) |

## Traps to Avoid

1. **Don't create an ORM-like abstraction over DynamoDB** - Keep it simple. Direct boto3 calls in the service layer. No "DynamoDB ORM" library.
2. **Don't try to replicate SQL JOINs** - DynamoDB is not relational. Denormalize where needed. Multiple queries are fine.
3. **Don't forget to handle DynamoDB's 1MB query limit** - Every query helper must loop on `LastEvaluatedKey`. Create a `query_all_pages()` utility.
4. **Don't use Scan for anything** - All access patterns must use Query with proper keys. Even the channels list uses GSI1 Query, not Scan.
5. **Don't change the API response shapes** - Frontend must continue working without changes. The migration is invisible to the client.
6. **Don't forget BatchWriteItem retry** - Always handle `UnprocessedItems` in the response with exponential backoff.
7. **Don't use app-layer filtering when FilterExpression works** - Use DynamoDB `FilterExpression` for pattern #8 (ticker filter) and pattern #14 (missing prices count) to reduce data transfer.
8. **Don't store timestamps as epoch numbers** - Use ISO 8601 strings consistently for correct lexicographic sorting in GSI sort keys.

## Dependencies
- boto3 (already in requirements.txt)
- DynamoDB Local Docker image (amazon/dynamodb-local)

## Acceptance Criteria
1. All 13 API endpoints return identical response shapes as before
2. MySQL Docker container replaced with DynamoDB Local
3. `docker compose up -d` + `python scripts/create_tables.py` starts the local environment
4. SQLAlchemy, PyMySQL, and Alembic fully removed from codebase
5. All existing tests pass with DynamoDB Local backend
6. Background processing pipeline (ThreadPoolExecutor) works correctly
7. Cascade delete works for channels (deletes videos, mentions, logs)
8. No frontend changes required
9. All query helpers handle DynamoDB's 1MB pagination limit
10. BatchWriteItem operations handle UnprocessedItems with retry

## Consultation Log

### Round 1 (Codex + Gemini)
- **Codex**: REQUEST_CHANGES - Missing GSI specs (key types, projections), pagination semantics, table naming, batch retry handling
- **Gemini**: COMMENT - Use FilterExpression instead of app-layer filtering, simplify cascade delete, drop counter table

**Changes made**:
- Added explicit key types (String) and projection types (ALL/KEYS_ONLY) for all GSIs
- Clarified table naming convention: `{prefix}`, `{prefix}-Stocks`
- Removed counter table - using `LOG#{iso_timestamp}#{uuid_suffix}` for log ordering
- Changed access pattern #8 to use `FilterExpression` instead of app-layer filtering
- Added `Select=COUNT` for pattern #14 to avoid transferring items
- Documented pagination ordering (created_at DESC) and eventual consistency
- Added BatchWriteItem retry handling with exponential backoff
- Changed healthcheck from `curl` to `wget` (DynamoDB Local image compatibility)
- Added thread safety details (shared resource, per-thread Table references)
- Added credential handling section (dummy creds for local, IAM for prod)
- Added timestamp format section (ISO 8601 with Z suffix)
- Added test isolation with unique per-test table prefixes
- Fixed "single-table design with 3 tables" terminology → "main single-table + 2 auxiliary tables" → simplified to 2 tables (removed counter table)
