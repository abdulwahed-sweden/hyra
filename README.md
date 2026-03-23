# Hyra — Rental Platform Demo

A production-quality rental marketplace API and dashboard built with Django, demonstrating senior-level backend engineering.

## English

### Stack

| Layer | Technology |
|---|---|
| Language | Python 3.12 |
| Framework | Django 4.2, Django REST Framework |
| Database | PostgreSQL 16 |
| Search | Elasticsearch 8 |
| Cache/Broker | Redis 7 |
| Containerization | Docker & Docker Compose |

### Quick Start

```bash
# Clone and start all services
git clone https://github.com/abdulwahed-sweden/hyra.git
cd hyra
docker compose up --build
```

The app starts at **http://localhost:8000** with 60 pre-seeded listings and queue entries.

### API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/listings/` | List active listings (filterable, searchable, paginated) |
| GET | `/api/listings/stats/` | Aggregate listing statistics |
| GET | `/api/listings/{id}/` | Listing detail |
| GET | `/api/listings/{id}/similar/` | Similar listings (same municipality + rooms) |
| POST | `/api/queue/entries/process/` | Run queue engine for a listing |
| GET | `/api/queue/entries/leaderboard/?listing={id}` | Ranked queue entries |
| GET | `/api/queue/entries/stats/` | Queue aggregate statistics |
| GET | `/api/search/?q={term}` | Full-text search (ES + Postgres fallback) |
| POST | `/api/search/index/` | Bulk index listings into Elasticsearch |
| GET | `/api/applications/` | List applications |
| POST | `/api/applications/` | Submit an application |

### Architecture Decisions

- **QueueEngine** — Pure Python class with explicit business logic. No signals or Django magic. Every step (eligibility, ranking, selection) is independently testable.
- **select_for_update()** — Prevents race conditions during queue processing.
- **transaction.atomic()** — Ensures the entire queue processing pipeline succeeds or rolls back.
- **Reproducible lottery** — Seeded with listing PK so the same listing always produces the same lottery order (auditable).
- **Elasticsearch fallback** — If ES is unavailable, search silently falls back to Postgres ILIKE queries. The response includes an `engine` field indicating which backend served the results.
- **Denormalized applicant snapshots** — Queue entries store applicant data at application time, preventing data drift.

### Dashboard

Single-page vanilla JS dashboard with five tabs:

1. **Bostäder** (Listings) — Card grid with search, filters, pagination
2. **Kömotor** (Queue Engine) — Process a listing's queue and view ranked results
3. **Sök** (Search) — Elasticsearch full-text search with facets
4. **Analys** (Analytics) — Stats overview with district and queue breakdowns
5. **API** — Interactive endpoint documentation

---

## Svenska / Swedish

### Snabbstart

```bash
git clone https://github.com/abdulwahed-sweden/hyra.git
cd hyra
docker compose up --build
```

Appen startar på **http://localhost:8000** med 60 förinspelade bostadsannonser.

### Teknikstack

| Lager | Teknik |
|---|---|
| Språk | Python 3.12 |
| Ramverk | Django 4.2, Django REST Framework |
| Databas | PostgreSQL 16 |
| Sökning | Elasticsearch 8 |
| Cache/Meddelandehanterare | Redis 7 |
| Containerisering | Docker & Docker Compose |

### API-endpoints

| Metod | Endpoint | Beskrivning |
|---|---|---|
| GET | `/api/listings/` | Lista aktiva bostäder (filtrering, sökning, paginering) |
| GET | `/api/listings/stats/` | Aggregerad statistik |
| GET | `/api/listings/{id}/` | Bostadsdetaljer |
| POST | `/api/queue/entries/process/` | Kör kömotorn för en bostad |
| GET | `/api/queue/entries/leaderboard/?listing={id}` | Rankade köplatser |
| GET | `/api/search/?q={term}` | Fulltextsökning (ES + Postgres-fallback) |
| GET | `/api/applications/` | Lista ansökningar |

### Arkitekturbeslut

- **QueueEngine** — Ren Python-klass utan signaler eller magi. Varje steg är separat testbart.
- **select_for_update()** — Förhindrar race conditions vid köbearbetning.
- **Reproducerbar lottning** — Seedas med bostadens PK för reviderbarhet.
- **Elasticsearch-fallback** — Sökningen faller tyst tillbaka till Postgres vid ES-avbrott.

---

## Om projektet / About

**Hyra** (Swedish: "rent") is a senior backend engineering demo targeting the HomeQ Senior Backend Engineer opening in Stockholm.

Built with HomeQ's exact stack: Python, Django, PostgreSQL, Elasticsearch. The queue engine is the centerpiece — showing architectural thinking, explicit business logic, and production patterns.

**Författare / Author:** Abdulwahed Mansour
**Plats / Location:** Norsborg, Stockholm, Sweden
**Kontakt / Contact:** abdulwahed.mansour@gmail.com · +46 76 930 8145
**GitHub:** github.com/abdulwahed-sweden
