---
title: Hyra
emoji: 🏠
colorFrom: blue
colorTo: green
sdk: docker
app_port: 7860
---

# Hyra — Rental Queue Engine

[![Python](https://img.shields.io/badge/Python-3.12-3776ab?logo=python&logoColor=white)](https://python.org)
[![Django](https://img.shields.io/badge/Django-4.2_LTS-092e20?logo=django&logoColor=white)](https://djangoproject.com)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169e1?logo=postgresql&logoColor=white)](https://postgresql.org)
[![Elasticsearch](https://img.shields.io/badge/Elasticsearch-8-005571?logo=elasticsearch&logoColor=white)](https://elastic.co)
[![Redis](https://img.shields.io/badge/Redis-7-dc382d?logo=redis&logoColor=white)](https://redis.io)
[![Tests](https://img.shields.io/badge/Tests-59_passing-brightgreen?logo=pytest&logoColor=white)](#tests)
[![Docker](https://img.shields.io/badge/Docker-Ready-2496ed?logo=docker&logoColor=white)](docker-compose.yml)
[![PyForge](https://img.shields.io/badge/PyForge-0.1.3-ff6b35?logo=rust&logoColor=white)](https://pypi.org/project/pyforge-django/)
[![License](https://img.shields.io/badge/License-MIT-yellow)](LICENSE)

A backend engineering demo targeting the **Senior Backend Engineer** role at [HomeQ](https://homeq.se) (Vend/Schibsted). Built with HomeQ's exact stack to demonstrate queue-based tenant selection, architectural decision-making, and production patterns. Serialization hot paths accelerated by [PyForge](https://github.com/abdulwahed-sweden/pyforge) — Rust-native DRF serialization delivering 2.5x throughput on queue leaderboard and application endpoints.

> **Live demo:** [abdulwahed-sweden-hyra.hf.space](https://abdulwahed-sweden-hyra.hf.space) | Local: `docker compose up --build` → [localhost:8000](http://localhost:8000)

---

## Quick Start

**Docker (recommended):**
```bash
git clone https://github.com/abdulwahed-sweden/hyra.git
cd hyra
docker compose up --build
# → http://localhost:8000       (project overview)
# → http://localhost:8000/dashboard/  (interactive dashboard)
```

**Native (macOS/Linux):**
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
# Requires: PostgreSQL running, createdb hyra_demo
python manage.py migrate
python manage.py seed_demo --clear
python manage.py test              # 59 tests
python manage.py runserver         # http://localhost:8000
```

---

## Project Structure

```
hyra/
├── apps/
│   ├── queue/           ← Queue engine (the centerpiece)
│   │   ├── models.py       QueueEngine, QueueEntry, QueueConfig
│   │   └── serializers.py  QueueEntrySerializer + PyForge mixin (2.5x)
│   ├── listings/        ← Landlord, Municipality, Listing + REST API
│   ├── search/          ← Elasticsearch with Postgres ILIKE fallback
│   ├── webhooks/        ← Event delivery to landlord systems
│   └── applications/    ← Tenant application submissions + PyForge mixin (2.6x)
├── tests/
│   ├── test_queue_engine.py   27 tests — eligibility, ranking, edge cases
│   ├── test_api.py            22 tests — endpoints, validation, errors
│   └── test_webhooks.py       10 tests — events, retry, HMAC, integration
├── config/              ← Django settings, URLs, WSGI
├── templates/           ← base.html, navbar, footer, dashboard, landing
└── docker-compose.yml   ← PostgreSQL + Redis + Elasticsearch + Web
```

---

## Queue Engine

**`apps/queue/models.py`** — The core of the project. A pure Python class with no signals, no magic.

```python
engine = QueueEngine(listing)
result = engine.process()
# → {"qualified": 5, "disqualified": 3, "winner": "Erik Andersson", "queue_type": "points"}
```

### What `process()` does in one `transaction.atomic()` call:

1. **Lock** — `select_for_update()` prevents concurrent processing of the same queue
2. **Eligibility** — Six rules checked in priority order (debt → income → household → BankID → credit → points)
3. **Rank** — Dispatch to the configured ranking algorithm
4. **Select** — Top-ranked applicant becomes winner, rest rejected
5. **Notify** — Emit webhook events to landlord systems

### Three Ranking Algorithms

| Type | Logic | Real-world use |
|------|-------|----------------|
| **Points** | Sorted by queue days, highest first | Traditional Swedish bostadskö — 1 point = 1 day |
| **First Come** | Sorted by application timestamp | Fast-moving listings, ~20% of allocations |
| **Lottery** | `random.Random(listing.pk).shuffle()` — reproducible | Fair chance for everyone, auditable |

### Eligibility Pipeline

Each rule returns a specific disqualification reason. First failure wins:

| # | Rule | Example reason |
|---|------|---------------|
| 1 | Kronofogden debt records | `"Kronofogden debt records"` |
| 2 | Income < rent × multiplier | `"Insufficient income: 25,000 SEK < 30,000 SEK"` |
| 3 | Household size > maximum | `"Household size 5 > max 4"` |
| 4 | BankID not verified | `"BankID verification required"` |
| 5 | Credit score below threshold | `"Credit score 45.0 < minimum 60.0"` |
| 6 | Queue points below minimum | `"Queue points 200 < minimum 500"` |

---

## Webhook Events

**`apps/webhooks/models.py`** — Event delivery with retry for landlord integrations.

```python
emit_event("queue.processed", landlord_id, {"listing_id": 1, "winner": "..."})
emit_event("tenant.selected", landlord_id, {"listing_id": 1, "tenant_name": "..."})
```

| Feature | Detail |
|---------|--------|
| **Retry schedule** | 5min → 15min → 1h → 6h → 24h → 48h → 7 days → exhausted |
| **Signing** | HMAC-SHA256 — receivers verify payload authenticity |
| **Delivery** | Best-effort — webhook failures never block queue processing |

---

## Caching Strategy

**`apps/listings/views.py`** — Redis cache on the highest-traffic endpoint.

```python
cached = cache.get("listing_stats")  # 60s TTL
if cached:
    return Response(json.loads(cached))
```

Falls back gracefully if Redis is unavailable — cache is optional, never a single point of failure.

---

## Rust-Accelerated Serialization

**`pyforge-django`** — Drop-in mixin that moves DRF serialization from Python to Rust.

```python
from django_pyforge.serializers import RustSerializerMixin

class QueueEntrySerializer(RustSerializerMixin, serializers.ModelSerializer):
    class Meta:
        model = QueueEntry
        fields = [...]   # all 18 fields — no other changes needed
```

### Benchmark: DRF vs PyForge (`many=True`, median of 3 runs)

| Serializer | 1,000 | 5,000 | 10,000 | 20,000 |
|---|---|---|---|---|
| **QueueEntry (18 fields)** | | | | |
| DRF | 52ms | 271ms | 547ms | 1.08s |
| PyForge | 22ms | 108ms | 220ms | 432ms |
| Speedup | **2.4x** | **2.5x** | **2.5x** | **2.5x** |
| **Application (11 fields)** | | | | |
| DRF | 45ms | 227ms | 464ms | 920ms |
| PyForge | 18ms | 93ms | 177ms | 356ms |
| Speedup | **2.5x** | **2.4x** | **2.6x** | **2.6x** |

**How it works:** On `many=True` calls (leaderboard, list views), PyForge bypasses DRF's `ListSerializer` entirely. It calls Rust's `serialize_instance()` per record in a tight loop, patching in `id` and FK fields from Python. Field classification is cached per serializer class — zero per-instance overhead.

**Where it's applied:** `QueueEntrySerializer` and `ApplicationSerializer` — serializers with 80%+ simple model fields. `ListingListSerializer` is excluded (3 computed fields with custom sources make the hybrid path slower than pure DRF).

---

## Search with Fallback

**`apps/search/views.py`** — Elasticsearch first, Postgres ILIKE on any failure.

```
GET /api/search/?q=södermalm&max_rent=12000&rooms=2
→ {"engine": "elasticsearch", "count": 8, "facets": {...}}
→ {"engine": "postgres_fallback", "count": 8, "facets": {...}}
```

- Multi-match across title, description, district, municipality (weighted, boosted)
- Fuzziness: `AUTO` for Swedish typo handling
- Facets: district terms + rent statistics
- Response always includes `engine` field for transparency

---

## REST API

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/listings/` | Active listings — filterable, searchable, paginated |
| `GET` | `/api/listings/{id}/` | Detail with nested landlord & municipality |
| `GET` | `/api/listings/{id}/similar/` | Same municipality + room count (max 4) |
| `GET` | `/api/listings/stats/` | Aggregates (Redis cached 60s) |
| `POST` | `/api/queue/entries/process/` | Run queue engine → `{"listing_id": 1}` |
| `GET` | `/api/queue/entries/leaderboard/?listing=1` | Ranked results after processing |
| `GET` | `/api/queue/entries/stats/` | Queue aggregates |
| `GET` | `/api/search/?q=term` | Full-text search with facets |
| `POST` | `/api/search/index/` | Bulk index to Elasticsearch |
| `GET` | `/api/applications/` | Rental applications |
| `GET` | `/health/` | Health check |

**Filtering examples:**
```
GET /api/listings/?min_rent=8000&max_rent=15000&min_rooms=2&ordering=-rent_sek
GET /api/search/?q=vasastan&max_rent=12000&rooms=2&page=1
GET /api/queue/entries/?listing=1&status=selected
```

---

## Tests

```bash
python manage.py test tests -v2    # 59 tests, ~0.7s
```

| Test file | Count | Coverage |
|-----------|-------|----------|
| `test_queue_engine.py` | **27** | Eligibility rules (10), Points ranking (2), First-come (1), Lottery (2), Edge cases (6), Auto-config (1), Timestamps (1), Reprocessing (1), Priority order (1) |
| `test_api.py` | **22** | Listings CRUD (11), Queue endpoints (9), Search fallback (7), Health check (1), Input validation, Error codes |
| `test_webhooks.py` | **10** | Event emit (1), Filtering (2), HMAC signing (1), Retry escalation (1), Exhaustion (1), Delivery tracking (2), Queue integration (2) |

---

## Engineering Decisions

| Decision | Why |
|----------|-----|
| `select_for_update()` in `transaction.atomic()` | Prevents concurrent queue processing — critical when thousands hit a popular listing |
| Pure Python QueueEngine class | No signals, no model methods — every step independently testable |
| Webhook retry with exponential backoff | Landlord systems go down; 5min→7day ensures delivery without overwhelming |
| HMAC-SHA256 webhook signing | Receivers verify payload authenticity — essential for tenant selection events |
| Redis cache on stats | Highest-read endpoint cached 60s — prevents DB pressure at scale |
| Elasticsearch with silent Postgres fallback | Search always works; `engine` field gives transparency |
| Reproducible lottery seed | `random.Random(listing.pk)` — same listing = same order, auditable |
| Denormalized applicant snapshots | Queue entries freeze data at application time — prevents drift |
| JSON-only renderer | No browsable API — clean JSON responses, production behavior |
| Explicit serializer fields | No `fields = "__all__"` — prevents accidental data exposure |
| PyForge on high-volume serializers only | 2.5x on QueueEntry/Application; ListingList excluded — computed fields make hybrid path slower than pure DRF |

---

## Seed Data

```bash
python manage.py seed_demo --clear --listings 60 --applicants-per-listing 15
```

- **10** real Swedish landlords (Stena, Wallenstam, Balder, Riksbyggen, etc.)
- **8** Stockholm-region municipalities with realistic districts
- **60** listings with weighted room/rent/status distribution
- **~600** queue entries with varied eligibility profiles (10% debt, 80% BankID verified)

---

## About

**Hyra** (Swedish: *rent*) is a senior backend engineering demo targeting the [HomeQ Senior Backend Engineer](https://careers.homeq.se) role in Stockholm. Built with HomeQ's exact stack to demonstrate the kind of architectural decisions, code quality, and production patterns the role requires.

**Author:** Abdulwahed Mansour
**Location:** Stockholm, Sweden
**Email:** abdulwahed.mansour@gmail.com
**Phone:** +46 76 930 8145
**GitHub:** [github.com/abdulwahed-sweden](https://github.com/abdulwahed-sweden)
