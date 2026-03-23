# CLAUDE.md — Hyra Rental Platform Demo

> **Instructions for Claude Code.**
> Read this file completely before writing any code.
> This is the single source of truth for the entire project.

---

## 🎯 Project Mission

Build a production-quality rental marketplace API + dashboard that demonstrates
senior-level Django engineering. The target audience is **Robert Kessler (CTO, HomeQ)**.

The platform mirrors HomeQ's core domain:
- Landlords publish listings
- Applicants join queues
- A queue engine ranks and selects tenants
- Full-text search powered by Elasticsearch

**Stack:** Python 3.12 · Django 4.2 · DRF · PostgreSQL 16 · Elasticsearch 8 · Redis · Docker

---

## 📁 Project Structure

Build everything inside the current directory. Final layout:

```
hyra/                               ← repo root (current directory)
├── CLAUDE.md                       ← this file
├── README.md                       ← bilingual EN/SV documentation
├── README.sv.md                    ← Swedish README
├── Dockerfile
├── docker-compose.yml
├── manage.py
├── requirements.txt
├── .env.example
├── .gitignore
│
├── config/                         ← Django project config
│   ├── __init__.py
│   ├── settings.py
│   ├── urls.py
│   └── wsgi.py
│
├── apps/                           ← all Django applications
│   ├── __init__.py
│   │
│   ├── listings/                   ← core domain: properties
│   │   ├── __init__.py
│   │   ├── admin.py
│   │   ├── apps.py
│   │   ├── filters.py
│   │   ├── models.py
│   │   ├── serializers.py
│   │   ├── urls.py
│   │   ├── views.py
│   │   ├── migrations/
│   │   └── management/
│   │       └── commands/
│   │           └── seed_demo.py    ← populate with realistic Swedish data
│   │
│   ├── queue/                      ← queue engine: ranking logic
│   │   ├── __init__.py
│   │   ├── admin.py
│   │   ├── apps.py
│   │   ├── models.py               ← QueueEntry, QueueConfig, QueueEngine
│   │   ├── serializers.py
│   │   ├── urls.py
│   │   ├── views.py
│   │   └── migrations/
│   │
│   ├── search/                     ← Elasticsearch integration
│   │   ├── __init__.py
│   │   ├── apps.py
│   │   ├── documents.py            ← ES document definition
│   │   ├── urls.py
│   │   └── views.py
│   │
│   └── applications/               ← applicant submissions
│       ├── __init__.py
│       ├── admin.py
│       ├── apps.py
│       ├── models.py
│       ├── serializers.py
│       ├── urls.py
│       ├── views.py
│       └── migrations/
│
├── templates/
│   └── dashboard.html              ← single-page dashboard UI
│
└── static/
    ├── css/
    └── js/
```

---

## ⚙️ Step-by-Step Build Instructions

Follow these steps **in order**. Do not skip steps.

### STEP 1 — requirements.txt

```
Django==4.2.13
djangorestframework==3.15.1
django-filter==23.5
psycopg2-binary==2.9.9
elasticsearch-dsl==8.13.1
elasticsearch==8.13.1
python-decouple==3.8
Faker==24.11.0
gunicorn==22.0.0
whitenoise==6.6.0
django-cors-headers==4.3.1
celery==5.4.0
redis==5.0.4
```

---

### STEP 2 — config/settings.py

Key requirements:
- Use `python-decouple` for all env vars
- `TIME_ZONE = "Europe/Stockholm"` — always Stockholm time
- `LANGUAGE_CODE = "sv-se"`
- Database: PostgreSQL (host from env, default `db` for Docker)
- Elasticsearch: `ELASTICSEARCH_DSL` pointing to env `ELASTICSEARCH_URL`
- Celery broker: Redis via env `REDIS_URL`
- Whitenoise for static files
- INSTALLED_APPS: `apps.listings`, `apps.queue`, `apps.search`, `apps.applications`
- REST_FRAMEWORK pagination: 12 per page, DjangoFilterBackend + SearchFilter + OrderingFilter

```python
# config/settings.py skeleton
from pathlib import Path
from decouple import config

BASE_DIR = Path(__file__).resolve().parent.parent
SECRET_KEY = config("SECRET_KEY", default="dev-only-insecure-key")
DEBUG = config("DEBUG", default=True, cast=bool)
ALLOWED_HOSTS = config("ALLOWED_HOSTS", default="*").split(",")
TIME_ZONE = "Europe/Stockholm"
LANGUAGE_CODE = "sv-se"
USE_TZ = True
# ... complete the rest
```

---

### STEP 3 — apps/listings/models.py

Build three models:

#### Landlord
```python
class Landlord(models.Model):
    name        # CharField 200
    org_number  # CharField 20, unique (Swedish org nr format: XXXXXX-XXXX)
    website     # URLField, blank
    is_verified # BooleanField default False
    created_at  # DateTimeField auto_now_add
```

#### Municipality
```python
class Municipality(models.Model):
    name    # CharField 100
    county  # CharField 100, default "Stockholm"
    # Meta: ordering = ["name"], verbose_name_plural = "municipalities"
```

#### Listing (main model)
```python
class Listing(models.Model):
    # TextChoices:
    #   ListingType: apartment, room, house
    #   Status: active, closed, coming_soon

    # ForeignKeys: landlord (CASCADE), municipality (SET_NULL)

    # Location fields:
    #   street_address, district, postal_code, city

    # Property fields:
    #   listing_type, rooms, size_sqm, floor, total_floors
    #   has_elevator, has_balcony, has_parking, is_accessible, allows_pets (all BooleanField)

    # Financial:
    #   rent_sek (PositiveIntegerField)
    #   min_income_multiplier (FloatField default=3.0) — income must be X times rent
    #   max_household_size (PositiveSmallIntegerField default=6)

    # Status:
    #   status, available_from (DateField), application_deadline (DateField null)
    #   published_at (auto_now_add), updated_at (auto_now)

    # Content:
    #   title (CharField 300), description (TextField blank)

    # Meta:
    #   ordering = ["-published_at"]
    #   indexes on: (status, listing_type), (municipality, rent_sek), (rooms, size_sqm)

    # Property:
    @property
    def applicant_count(self):
        return self.queue_entries.count()
```

---

### STEP 4 — apps/queue/models.py

This is the most important file. Build carefully.

#### QueueType (TextChoices)
```
POINTS     = "points"      → ranked by accumulated queue days
FIRST_COME = "first_come"  → ranked by application timestamp
LOTTERY    = "lottery"     → reproducible random (seeded by listing pk)
```

#### QueueConfig (OneToOne → Listing)
```python
class QueueConfig(models.Model):
    listing              # OneToOneField Listing, related_name="queue_config"
    queue_type           # QueueType choices, default POINTS
    require_bankid       # BooleanField default True
    require_no_debt      # BooleanField default True
    min_credit_score     # FloatField default 60.0
    min_queue_points     # PositiveIntegerField null/blank
    created_at           # auto_now_add
```

#### QueueEntry
```python
class QueueEntry(models.Model):
    # Status choices: pending, qualified, disqualified, selected, rejected, withdrawn

    listing              # FK Listing, related_name="queue_entries"

    # Applicant snapshot (denormalized — snapshot at time of application):
    applicant_name       # CharField 200
    applicant_email      # EmailField
    monthly_income_sek   # PositiveIntegerField
    household_size       # PositiveSmallIntegerField default 1
    queue_points         # PositiveIntegerField default 0
    bankid_verified      # BooleanField default False
    credit_score         # FloatField default 50.0
    has_debt_records     # BooleanField default False
    preferred_districts  # CharField 500, blank

    # Queue state:
    status                    # Status choices, default pending
    disqualification_reason   # CharField 300, blank
    rank_score                # FloatField null/blank
    rank_position             # PositiveIntegerField null/blank
    applied_at                # auto_now_add
    processed_at              # DateTimeField null/blank

    # Meta:
    #   ordering = ["-queue_points", "applied_at"]
    #   unique_together = [["listing", "applicant_email"]]
    #   indexes on: (listing, status), (queue_points,)
```

#### QueueEngine (pure Python class, no Django magic)

```python
class QueueEngine:
    """
    Pure business logic. No signals, no magic.
    Explicit, testable, readable.

    Usage:
        engine = QueueEngine(listing)
        result = engine.process()
    """

    def __init__(self, listing): ...

    def process(self) -> dict:
        """
        1. Lock entries with select_for_update() inside transaction.atomic()
        2. Run _check_eligibility() on each PENDING entry
        3. Mark eligible → QUALIFIED, others → DISQUALIFIED with reason
        4. Run _rank() on qualified entries
        5. Assign rank_position and rank_score to each
        6. First = SELECTED, rest = REJECTED
        7. Return summary dict:
           {listing_id, queue_type, total, qualified, disqualified, winner, winner_score}
        """

    def _check_eligibility(self, entry) -> str:
        """
        Returns disqualification reason string, or "" if eligible.
        Hard rules (in order):
        1. has_debt_records → "Kronofogden debt records"
        2. income < rent * min_income_multiplier → "Insufficient income: X SEK < Y SEK"
        3. household_size > max_household_size → "Household size X > max Y"
        4. If config.require_bankid and not bankid_verified → "BankID verification required"
        5. credit_score < config.min_credit_score → "Credit score X < minimum Y"
        6. queue_points < config.min_queue_points → "Queue points X < minimum Y"
        """

    def _rank(self, entries) -> list:
        """Dispatch to the correct ranking method based on queue_type."""

    def _rank_by_points(self, entries) -> list:
        """
        Sort by queue_points descending.
        rank_score = (entry.queue_points / max_points) * 100
        """

    def _rank_by_first_come(self, entries) -> list:
        """
        Sort by applied_at ascending.
        rank_score = ((total - position) / total) * 100
        """

    def _rank_by_lottery(self, entries) -> list:
        """
        Reproducible shuffle: random.Random(self.listing.pk).shuffle(entries)
        rank_score = ((total - position) / total) * 100
        This ensures the same listing always produces the same lottery order.
        """
```

---

### STEP 5 — apps/listings/views.py

```python
class ListingViewSet(viewsets.ReadOnlyModelViewSet):
    # queryset: annotate applicant_count=Count("queue_entries"), filter status="active"
    # filterset_class: ListingFilter (min_rent, max_rent, min_rooms, max_rooms, district, etc.)
    # search_fields: title, street_address, district, description
    # ordering_fields: rent_sek, rooms, size_sqm, published_at, applicant_count

    # Extra actions:
    # @action stats() → aggregate: total, avg_rent, min_rent, max_rent, avg_size, by_type, by_district[:10]
    # @action similar() → same municipality + rooms, exclude self, limit 4
```

---

### STEP 6 — apps/queue/views.py

```python
class QueueViewSet(viewsets.ModelViewSet):
    # filterset_fields: listing, status
    # ordering_fields: queue_points, rank_position, applied_at

    # @action process(POST) → body: {listing_id} → run QueueEngine → return summary
    # @action leaderboard(GET) → ?listing=ID → return ranked entries + winner
    # @action stats(GET) → aggregate by status, avg points, avg credit score
```

---

### STEP 7 — apps/search/views.py

```python
class ListingSearchView(APIView):
    """
    GET /api/search/?q=södermalm&max_rent=12000&rooms=2

    1. Try Elasticsearch first:
       - multi_match: title^3, description, district^2, municipality^2, street_address
       - fuzziness: AUTO (handles Swedish typos)
       - filters: status=active, optional rent/rooms/balcony/pets
       - aggregations: by_district (terms, size=15), rent_stats (stats)

    2. On ANY exception → fall back to Postgres ILIKE silently
       (log warning, never raise to client)

    Response always includes:
       {count, page, results, facets, engine: "elasticsearch"|"postgres_fallback"}
    """

class IndexListingsView(APIView):
    """
    POST /api/search/index/
    Bulk index all active listings into Elasticsearch.
    Uses elasticsearch.helpers.bulk() for efficiency.
    """
```

---

### STEP 8 — apps/listings/management/commands/seed_demo.py

Seed the database with realistic Swedish data:

```
Landlords (10):
  Stena Fastigheter, Wallenstam, Balder, Ikano Bostad, Riksbyggen,
  Svenska Bostäder, Stockholmshem, Familjebostäder, Heba Fastigheter, Einar Mattsson

Municipalities (8):
  Stockholm, Solna, Sundbyberg, Nacka, Huddinge, Botkyrka, Järfälla, Täby

Districts per municipality (realistic):
  Stockholm: Södermalm, Vasastan, Kungsholmen, Östermalm, Hammarby Sjöstad,
             Liljeholmen, Bromma, Farsta, Tensta, Rinkeby, Vällingby, Enskede
  Solna: Hagalund, Huvudsta, Råsunda, Frösunda
  Botkyrka: Norsborg, Tumba, Hallunda, Alby
  (etc.)

Listings: 60 by default (--listings N to override)
  - Weighted room distribution: 1rm(20%), 2rm(35%), 3rm(25%), 4rm(15%), 5rm(5%)
  - Rent formula: base 4500 + (rooms * 2200) + (size * 35) + random(-800, 2000), rounded to 100
  - Queue type weights: points(55%), first_come(25%), lottery(20%)
  - Status weights: active(80%), active(10%), coming_soon(10%)
  - Random amenities, BankID requirements, credit thresholds

Queue entries per listing: 5–15 applicants
  - Realistic Swedish names (20 names pool)
  - Income: 22,000–85,000 SEK/month
  - Queue points: 0–5000 (representing days registered)
  - Credit score: 40–100
  - 10% chance of debt records (for disqualification demo)
  - 80% BankID verified

Management args:
  --listings N          (default 60)
  --applicants-per-listing N  (default 15)
  --clear               (delete all existing data first)
```

---

### STEP 9 — templates/dashboard.html

Single HTML file. No external JS frameworks. Vanilla JS only.

**Five tabs:**
1. **Listings** — card grid, search bar, rent/rooms filters, pagination
2. **Queue Engine** — input listing ID → POST /api/queue/entries/process/ → show results table
3. **Search** — Elasticsearch search box → show results + facet pills
4. **Analytics** — stat cards + top districts table + queue status breakdown
5. **API** — table of all endpoints with clickable links

**Design requirements:**
- Font: DM Serif Display (headings) + DM Sans (body) from Google Fonts
- Colors: --accent #0057ff, --green #00875a, --ink #0f1923, --surface #f4f6f8
- Status pills: selected=green, qualified=blue, disqualified=red, pending=amber
- Skeleton loaders while fetching
- Toast notifications for actions
- Responsive grid (auto-fill, min 310px columns)
- Header shows: logo + "Django · DRF · PostgreSQL · Elasticsearch"
- NO external CSS frameworks (no Bootstrap, no Tailwind)

---

### STEP 10 — docker-compose.yml

Four services:

```yaml
services:
  db:          # postgres:16-alpine, healthcheck pg_isready
  redis:       # redis:7-alpine, healthcheck redis-cli ping
  elasticsearch: # elasticsearch:8.13.4, security disabled, 512m heap
  web:         # build: ., depends on all three healthy
               # command: migrate → seed_demo --clear → collectstatic → gunicorn
               # ports: 8000:8000
               # TIME_ZONE handled by Django settings (Europe/Stockholm)
```

---

### STEP 11 — README.md (bilingual EN + SV)

Structure:
```
# Hyra — Rental Platform Demo

## English
[project description, stack table, quick start, API endpoints, architecture decisions]

---

## Svenska / Swedish
[Swedish translation of same content — clear, professional]

---

## Om projektet / About
[Brief bilingual note: built as senior backend demo for HomeQ opening]
```

---

## 🔧 Code Quality Rules

Apply these rules to **every file** you write:

### Python
```python
# 1. Every class gets a docstring explaining WHY it exists, not WHAT it does
class QueueEngine:
    """
    Processes a listing's applicant queue in a single atomic transaction.
    Separates eligibility checking from ranking — each step is independently testable.
    """

# 2. Every non-trivial method gets a one-line comment on the WHY
def _rank_by_lottery(self, entries):
    # Seed with listing pk so the same listing always produces the same order
    # (reproducible randomness — landlord can audit the result)
    rng = random.Random(self.listing.pk)

# 3. Type hints on all public methods
def process(self) -> dict:
def _check_eligibility(self, entry: QueueEntry) -> str:
def _rank(self, entries: list[QueueEntry]) -> list[QueueEntry]:

# 4. No bare except — always catch specific exceptions
try:
    response = s.execute()
except ConnectionError as exc:
    logger.warning("Elasticsearch unavailable: %s", exc)
    return self._postgres_fallback(...)

# 5. Use select_related / prefetch_related — never N+1 queries
queryset = Listing.objects.select_related("landlord", "municipality")

# 6. Explicit over implicit — no clever one-liners that need decoding
```

### Django specifics
```python
# Use select_for_update() in QueueEngine.process() — prevent race conditions
entries = QueueEntry.objects.select_for_update().filter(...)

# Wrap queue processing in transaction.atomic()
with transaction.atomic():
    ...

# Always use update_fields when saving specific fields
entry.save(update_fields=["status", "processed_at"])

# Index fields that are filtered/ordered frequently
class Meta:
    indexes = [
        models.Index(fields=["status", "listing_type"]),
        models.Index(fields=["municipality", "rent_sek"]),
    ]
```

### Naming
```
Models:        PascalCase (Listing, QueueEntry, QueueEngine)
Views:         PascalCase + suffix (ListingViewSet, QueueViewSet, ListingSearchView)
Serializers:   PascalCase + suffix (ListingListSerializer, ListingDetailSerializer)
URL names:     kebab-case (listing-list, queue-process, listing-search)
Management:    snake_case (seed_demo.py)
```

---

## 🕐 Time Zone

All datetime handling uses Stockholm time:
```python
# settings.py
TIME_ZONE = "Europe/Stockholm"
USE_TZ = True

# In code — always use timezone.now(), never datetime.now()
from django.utils import timezone
entry.processed_at = timezone.now()

# In seed data — dates relative to today in Stockholm
from django.utils import timezone
today = timezone.localdate()  # Stockholm date
available_from = today + timedelta(days=random.randint(14, 90))
```

---

## 🌐 Language Rules

| File | Language |
|---|---|
| Python code, comments, docstrings | English |
| README.md | English + Swedish (bilingual) |
| README.sv.md | Swedish only |
| Dashboard UI text | Swedish (it's a Swedish platform) |
| Django admin verbose_name | Swedish where natural |
| API field names | English (REST convention) |
| Seed data (names, districts, streets) | Swedish/realistic |
| Git commit messages | English |

---

## 🐛 Common Pitfalls — Avoid These

```python
# ❌ WRONG — N+1 query
for listing in Listing.objects.all():
    print(listing.landlord.name)  # hits DB each time

# ✅ RIGHT
for listing in Listing.objects.select_related("landlord"):
    print(listing.landlord.name)

# ❌ WRONG — naive datetime in Stockholm
from datetime import datetime
now = datetime.now()

# ✅ RIGHT — timezone-aware Stockholm time
from django.utils import timezone
now = timezone.now()

# ❌ WRONG — bare except swallows all errors
try:
    result = es.search(...)
except:
    pass

# ✅ RIGHT — catch specific, log, fallback
try:
    result = es.search(...)
except Exception as exc:
    logger.warning("ES unavailable, falling back to Postgres: %s", exc)
    return self._postgres_fallback(...)

# ❌ WRONG — saving whole object when only one field changed
entry.status = "selected"
entry.save()

# ✅ RIGHT
entry.status = "selected"
entry.save(update_fields=["status"])
```

---

## ✅ Build Checklist

Work through this list top to bottom. Check each before moving to the next.

- [ ] `requirements.txt` — all packages pinned
- [ ] `config/settings.py` — TIME_ZONE=Europe/Stockholm, decouple, all apps registered
- [ ] `config/urls.py` — all 4 app url includes + dashboard template view
- [ ] `config/wsgi.py`
- [ ] `manage.py`
- [ ] `apps/listings/models.py` — Landlord, Municipality, Listing with indexes
- [ ] `apps/listings/serializers.py` — List + Detail serializers
- [ ] `apps/listings/filters.py` — ListingFilter with min/max rent, rooms, size, district
- [ ] `apps/listings/views.py` — ListingViewSet + stats + similar actions
- [ ] `apps/listings/urls.py`
- [ ] `apps/listings/admin.py`
- [ ] `apps/listings/management/commands/seed_demo.py` — 60 listings + queue entries
- [ ] `apps/queue/models.py` — QueueConfig, QueueEntry, QueueEngine (the star)
- [ ] `apps/queue/serializers.py`
- [ ] `apps/queue/views.py` — process + leaderboard + stats actions
- [ ] `apps/queue/urls.py`
- [ ] `apps/queue/admin.py`
- [ ] `apps/search/views.py` — ES search + Postgres fallback + bulk index
- [ ] `apps/search/urls.py`
- [ ] `apps/applications/models.py` — Application model
- [ ] `apps/applications/serializers.py`
- [ ] `apps/applications/views.py`
- [ ] `apps/applications/urls.py`
- [ ] `apps/applications/admin.py`
- [ ] `templates/dashboard.html` — 5 tabs, vanilla JS, Swedish UI text
- [ ] `docker-compose.yml` — db + redis + elasticsearch + web, all with healthchecks
- [ ] `Dockerfile`
- [ ] `README.md` — bilingual EN + SV
- [ ] `README.sv.md` — Swedish only
- [ ] `.env.example`
- [ ] `.gitignore`
- [ ] All `migrations/__init__.py` files exist
- [ ] All `apps.py` files exist with correct AppConfig

---

## 🚀 Final Verification

After building everything, verify:

```bash
# 1. Docker starts cleanly
docker compose up --build

# 2. Seed data loaded
curl http://localhost:8000/api/listings/stats/
# Expected: {"total": 60, "avg_rent": ~9500, ...}

# 3. Queue engine works
curl -X POST http://localhost:8000/api/queue/entries/process/ \
  -H "Content-Type: application/json" \
  -d '{"listing_id": 1}'
# Expected: {"qualified": N, "disqualified": M, "winner": "...", ...}

# 4. Search works (may fall back to Postgres if ES still indexing)
curl "http://localhost:8000/api/search/?q=södermalm"
# Expected: {"count": N, "engine": "elasticsearch"|"postgres_fallback", ...}

# 5. Dashboard loads
open http://localhost:8000
# Expected: Hyra dashboard with 5 tabs, listing cards, stats

# 6. Admin accessible
open http://localhost:8000/admin
```

---

## 📝 About This Project

**Hyra** (Swedish: "rent/hire") is a senior backend engineering demo
targeting the HomeQ Senior Backend Engineer opening (Stockholm, hybrid).

Built with HomeQ's exact stack: Python · Django · PostgreSQL · Elasticsearch.
The queue engine is the centerpiece — it shows architectural thinking,
explicit business logic, and production patterns (select_for_update,
transaction.atomic, reproducible randomness).

**Author:** Abdulwahed Mansour
**Location:** Norsborg, Stockholm, Sweden
**Contact:** abdulwahed.mansour@gmail.com · +46 76 930 8145
**GitHub:** github.com/abdulwahed-sweden

---

*End of CLAUDE.md — start building from STEP 1 and work through the checklist.*
