# Hyra — Rental Queue Engine

A backend engineering demo built with HomeQ's stack: **Python 3.12 · Django 4.2 · PostgreSQL 16 · Elasticsearch 8 · Redis 7**.

Demonstrates queue-based tenant selection with eligibility filtering, three ranking algorithms, webhook event delivery with retry logic, Redis caching, and Elasticsearch with automatic Postgres fallback. **59 tests passing.**

---

## Quick Start

```bash
docker compose up --build          # http://localhost:8000
```

Or natively:

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate && python manage.py seed_demo --clear
python manage.py test              # 59 tests
python manage.py runserver
```

---

## Architecture

```
apps/
├── queue/           Queue engine — eligibility, ranking, selection
│   └── models.py    QueueEngine, QueueEntry, QueueConfig
├── listings/        Landlord, Municipality, Listing models + filtered API
├── search/          Elasticsearch with silent Postgres ILIKE fallback
├── webhooks/        Event delivery to landlord systems with retry logic
├── applications/    Tenant application submissions
tests/
├── test_queue_engine.py    27 tests — eligibility, ranking, edge cases
├── test_api.py             22 tests — endpoints, validation, errors
├── test_webhooks.py        10 tests — events, retry, HMAC, integration
```

---

## Queue Engine

**`apps/queue/models.py`** — The core. A pure Python class with explicit business logic.

```python
engine = QueueEngine(listing)
result = engine.process()
# {"qualified": 5, "disqualified": 3, "winner": "Erik Andersson", "queue_type": "points"}
```

### What `process()` does in one `transaction.atomic()` call:

1. **Lock** — `select_for_update()` prevents concurrent processing of the same queue
2. **Eligibility** — Six rules checked in priority order (debt → income → household → BankID → credit → points)
3. **Rank** — Dispatch to points/first-come/lottery algorithm
4. **Select** — Top-ranked applicant becomes winner, rest rejected
5. **Notify** — Emit webhook events to landlord systems

### Ranking Algorithms

| Type | Logic | Real-world use |
|------|-------|----------------|
| `points` | Sorted by queue days, highest first | Traditional Swedish bostadskö — 1 point = 1 day |
| `first_come` | Sorted by application timestamp | Fast-moving listings, 20%+ of HomeQ allocations |
| `lottery` | `random.Random(listing.pk).shuffle()` — reproducible | Fair chance, auditable by re-running with same seed |

### Eligibility Pipeline

Each rule returns a specific disqualification reason. First failure wins — mirroring real property management requirements:

1. **Kronofogden debt records** → automatic reject
2. **Income < rent × multiplier** → "Insufficient income: 25,000 SEK < 30,000 SEK"
3. **Household size > maximum** → "Household size 5 > max 4"
4. **BankID not verified** (when required) → "BankID verification required"
5. **Credit score below threshold** → "Credit score 45.0 < minimum 60.0"
6. **Queue points below minimum** (when set) → "Queue points 200 < minimum 500"

---

## Webhook Events

**`apps/webhooks/models.py`** — Event delivery system for landlord integrations.

When a queue is processed, the platform notifies landlord systems via webhooks. This mirrors the integration pattern needed when 1000+ property companies depend on your platform.

```python
# Automatically emitted after queue processing:
emit_event("queue.processed", landlord_id, {"listing_id": 1, "winner": "..."})
emit_event("tenant.selected", landlord_id, {"listing_id": 1, "tenant_name": "..."})
```

**Retry with exponential backoff:** 5min → 15min → 1h → 6h → 24h → 48h → 7 days → exhausted.

**HMAC-SHA256 signing:** Every payload is signed with the endpoint's secret so receivers can verify authenticity.

**Best-effort delivery:** Webhook failures never block queue processing — the queue is the critical path.

---

## Caching Strategy

**`apps/listings/views.py`** — Redis cache on the stats endpoint.

The `/api/listings/stats/` endpoint is the highest-traffic read path (called by dashboard, landing page, analytics on every load). With 1.2M users, this query would hammer the database.

```python
# 60-second TTL — data changes infrequently, reads are constant
cached = cache.get("listing_stats")
if cached:
    return Response(json.loads(cached))
```

Falls back gracefully if Redis is unavailable — cache is optional, never a single point of failure.

---

## Search with Fallback

**`apps/search/views.py`** — Elasticsearch first, Postgres ILIKE on any failure.

```
GET /api/search/?q=södermalm&max_rent=12000&rooms=2
→ {"engine": "elasticsearch", "count": 8, "facets": {...}}  # or
→ {"engine": "postgres_fallback", "count": 8, "facets": {...}}
```

- Multi-match across title, description, district, municipality (weighted)
- Fuzziness for Swedish typo handling
- District facets + rent stats aggregations
- Response always includes `engine` field so client knows which backend served results

---

## API

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/listings/` | Active listings — filterable, searchable, paginated |
| `GET` | `/api/listings/{id}/` | Detail with nested landlord/municipality |
| `GET` | `/api/listings/{id}/similar/` | Same municipality + rooms |
| `GET` | `/api/listings/stats/` | Cached aggregates |
| `POST` | `/api/queue/entries/process/` | Run queue engine |
| `GET` | `/api/queue/entries/leaderboard/?listing=1` | Ranked results |
| `GET` | `/api/search/?q=term` | Full-text search |
| `GET` | `/health/` | Health check |

---

## Tests — 59 passing

```
tests/test_queue_engine.py     27 tests
  EligibilityTests              10  — each rule independently, priority order, boundaries
  PointsRankingTests             2  — highest wins, score normalization
  FirstComeRankingTests          1  — earliest application wins
  LotteryRankingTests            2  — reproducible, valid output
  ProcessEdgeCaseTests           6  — empty queue, all disqualified, reprocessing, auto-config

tests/test_api.py              22 tests
  ListingAPITests               11  — CRUD, filtering, ordering, search, pagination, 404
  QueueAPITests                  9  — process, leaderboard, validation, error codes
  SearchAPITests                 7  — fallback, facets, page validation, engine field

tests/test_webhooks.py         10 tests
  WebhookModelTests              8  — emit, filter, HMAC, retry escalation, exhaustion
  WebhookQueueIntegrationTests   2  — events emitted on process, works without endpoints
```

---

## Engineering Decisions

| Decision | Why |
|----------|-----|
| `select_for_update()` in `transaction.atomic()` | Prevents two requests from processing the same queue — critical when thousands hit a popular listing simultaneously |
| Pure Python QueueEngine class | No signals, no model methods — every step independently testable and debuggable |
| Webhook retry with exponential backoff | Landlord systems go down; 5min→7day schedule ensures delivery without overwhelming failed endpoints |
| HMAC-SHA256 webhook signing | Receivers verify payload authenticity — essential when handling tenant selection events |
| Redis cache on stats | Highest-read endpoint cached for 60s — prevents DB pressure from dashboard/analytics polling |
| ES with silent Postgres fallback | Search always works; `engine` field gives transparency without exposing infrastructure failures to users |
| Reproducible lottery seed | `random.Random(listing.pk)` — same listing always produces same order, so landlords can audit results |
| Denormalized applicant snapshots | Queue entries freeze income/credit at application time — prevents data drift if profile changes after applying |

---

## Stack

Python 3.12 · Django 4.2 LTS · Django REST Framework 3.15 · PostgreSQL 16 · Elasticsearch 8 · Redis 7 · Docker Compose

---

Built by **Abdulwahed Mansour** · Stockholm · abdulwahed.mansour@gmail.com · [github.com/abdulwahed-sweden](https://github.com/abdulwahed-sweden)
