# Hyra — Bostadsplattform Demo

En produktionsklar bostadsmarknadsplats med API och instrumentpanel, byggd med Django för att demonstrera senior backend-kompetens.

## Teknikstack

| Lager | Teknik |
|---|---|
| Språk | Python 3.12 |
| Ramverk | Django 4.2, Django REST Framework |
| Databas | PostgreSQL 16 |
| Sökning | Elasticsearch 8 |
| Cache/Meddelandehanterare | Redis 7 |
| Containerisering | Docker & Docker Compose |

## Snabbstart

```bash
git clone https://github.com/abdulwahed-sweden/hyra.git
cd hyra
docker compose up --build
```

Appen startar på **http://localhost:8000** med 60 förinspelade bostadsannonser och köplatser.

## API-endpoints

| Metod | Endpoint | Beskrivning |
|---|---|---|
| GET | `/api/listings/` | Lista aktiva bostäder (filtrering, sökning, paginering) |
| GET | `/api/listings/stats/` | Aggregerad statistik för bostäder |
| GET | `/api/listings/{id}/` | Bostadsdetaljer |
| GET | `/api/listings/{id}/similar/` | Liknande bostäder (samma kommun och antal rum) |
| POST | `/api/queue/entries/process/` | Kör kömotorn för en bostad |
| GET | `/api/queue/entries/leaderboard/?listing={id}` | Rankade köplatser |
| GET | `/api/queue/entries/stats/` | Aggregerad köstatistik |
| GET | `/api/search/?q={term}` | Fulltextsökning (Elasticsearch med Postgres-fallback) |
| POST | `/api/search/index/` | Massindexera bostäder i Elasticsearch |
| GET | `/api/applications/` | Lista ansökningar |
| POST | `/api/applications/` | Skicka in en ansökan |

## Instrumentpanel

En ensidig instrumentpanel med vanilla JavaScript och fem flikar:

1. **Bostäder** — Kortvyn med sökning, filter och paginering
2. **Kömotor** — Bearbeta en bostads kö och visa rankade resultat
3. **Sök** — Elasticsearch-sökning med facetter
4. **Analys** — Statistiköversikt med områdes- och köfördelning
5. **API** — Interaktiv endpoint-dokumentation

## Arkitekturbeslut

- **QueueEngine** — Ren Python-klass med explicit affärslogik. Inga signaler eller magi. Varje steg (behörighetskontroll, rankning, urval) är oberoende testbart.
- **select_for_update()** — Förhindrar race conditions vid köbearbetning.
- **transaction.atomic()** — Säkerställer att hela köbearbetningen lyckas eller återställs.
- **Reproducerbar lottning** — Seedas med bostadens primärnyckel så att samma bostad alltid producerar samma lottningsordning (reviderbart).
- **Elasticsearch-fallback** — Om ES är otillgängligt faller sökningen tyst tillbaka till Postgres ILIKE-frågor. Svaret inkluderar ett `engine`-fält som anger vilken backend som serverade resultaten.
- **Denormaliserade sökande-snapshots** — Köplatser lagrar sökandedata vid ansökningstillfället för att förhindra datadrift.

## Om projektet

**Hyra** (svenska: "hyra") är en senior backend engineering-demo riktad mot HomeQ Senior Backend Engineer-tjänsten i Stockholm.

Byggd med HomeQs exakta teknikstack: Python, Django, PostgreSQL, Elasticsearch. Kömotorn är kärnan — den visar arkitektoniskt tänkande, explicit affärslogik och produktionsmönster.

**Författare:** Abdulwahed Mansour
**Plats:** Norsborg, Stockholm
**Kontakt:** abdulwahed.mansour@gmail.com · +46 76 930 8145
**GitHub:** github.com/abdulwahed-sweden
