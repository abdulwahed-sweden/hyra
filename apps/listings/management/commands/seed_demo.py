"""
Populate the database with realistic Swedish rental data.

Creates landlords, municipalities, listings with queue configs,
and queue entries with varied applicant profiles.
"""
import random
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.listings.models import Landlord, Listing, Municipality
from apps.queue.models import QueueConfig, QueueEntry, QueueType


# --- Seed data pools ---

LANDLORDS = [
    ("Stena Fastigheter", "556004-8789"),
    ("Wallenstam", "556072-1523"),
    ("Balder", "556525-6905"),
    ("Ikano Bostad", "556132-6303"),
    ("Riksbyggen", "702001-7781"),
    ("Svenska Bostäder", "556043-6429"),
    ("Stockholmshem", "556035-9555"),
    ("Familjebostäder", "556035-6428"),
    ("Heba Fastigheter", "556018-8418"),
    ("Einar Mattsson", "556007-3456"),
]

MUNICIPALITIES = {
    "Stockholm": {
        "county": "Stockholm",
        "districts": [
            "Södermalm", "Vasastan", "Kungsholmen", "Östermalm",
            "Hammarby Sjöstad", "Liljeholmen", "Bromma", "Farsta",
            "Tensta", "Rinkeby", "Vällingby", "Enskede",
        ],
    },
    "Solna": {
        "county": "Stockholm",
        "districts": ["Hagalund", "Huvudsta", "Råsunda", "Frösunda"],
    },
    "Sundbyberg": {
        "county": "Stockholm",
        "districts": ["Hallonbergen", "Rissne", "Ursvik", "Centrala Sundbyberg"],
    },
    "Nacka": {
        "county": "Stockholm",
        "districts": ["Nacka Strand", "Saltsjöbaden", "Fisksätra", "Sickla"],
    },
    "Huddinge": {
        "county": "Stockholm",
        "districts": ["Flemingsberg", "Stuvsta", "Trångsund", "Sjödalen"],
    },
    "Botkyrka": {
        "county": "Stockholm",
        "districts": ["Norsborg", "Tumba", "Hallunda", "Alby"],
    },
    "Järfälla": {
        "county": "Stockholm",
        "districts": ["Jakobsberg", "Barkarby", "Kallhäll", "Viksjö"],
    },
    "Täby": {
        "county": "Stockholm",
        "districts": ["Täby Centrum", "Gribbylund", "Näsby Park", "Arninge"],
    },
}

STREETS = [
    "Sveavägen", "Götgatan", "Hornsgatan", "Birger Jarlsgatan",
    "Odengatan", "Kungsgatan", "Drottninggatan", "Strandvägen",
    "Fleminggatan", "Sankt Eriksgatan", "Ringvägen", "Folkungagatan",
    "Karlavägen", "Valhallavägen", "Norrtullsgatan", "Bondegatan",
    "Scheelegatan", "Hantverkargatan", "Kungsholmsgatan", "Söder Mälarstrand",
]

SWEDISH_FIRST_NAMES = [
    "Erik", "Anna", "Lars", "Maria", "Karl", "Karin", "Johan",
    "Eva", "Anders", "Lena", "Nils", "Sara", "Per", "Emma",
    "Olof", "Kristina", "Gustaf", "Ingrid", "Sven", "Helena",
]

SWEDISH_LAST_NAMES = [
    "Andersson", "Johansson", "Karlsson", "Nilsson", "Eriksson",
    "Larsson", "Olsson", "Persson", "Svensson", "Gustafsson",
    "Pettersson", "Jonsson", "Lindberg", "Lindström", "Lindgren",
    "Bergström", "Fredriksson", "Sandberg", "Henriksson", "Forsberg",
]

# Room distribution: 1rm=20%, 2rm=35%, 3rm=25%, 4rm=15%, 5rm=5%
ROOM_WEIGHTS = [1] * 20 + [2] * 35 + [3] * 25 + [4] * 15 + [5] * 5

# Queue type weights: points=55%, first_come=25%, lottery=20%
QUEUE_TYPE_WEIGHTS = (
    [QueueType.POINTS] * 55
    + [QueueType.FIRST_COME] * 25
    + [QueueType.LOTTERY] * 20
)

# Status weights: active=80%, closed=10%, coming_soon=10%
STATUS_WEIGHTS = (
    [Listing.Status.ACTIVE] * 80
    + [Listing.Status.CLOSED] * 10
    + [Listing.Status.COMING_SOON] * 10
)


class Command(BaseCommand):
    help = "Seed database with realistic Swedish rental data"

    def add_arguments(self, parser):
        parser.add_argument(
            "--listings", type=int, default=60,
            help="Number of listings to create (default: 60)",
        )
        parser.add_argument(
            "--applicants-per-listing", type=int, default=15,
            help="Max applicants per listing (default: 15)",
        )
        parser.add_argument(
            "--clear", action="store_true",
            help="Delete all existing data before seeding",
        )

    def handle(self, *args, **options):
        num_listings = options["listings"]
        max_applicants = options["applicants_per_listing"]

        if options["clear"]:
            self.stdout.write("Clearing existing data...")
            QueueEntry.objects.all().delete()
            QueueConfig.objects.all().delete()
            Listing.objects.all().delete()
            Landlord.objects.all().delete()
            Municipality.objects.all().delete()

        landlords = self._create_landlords()
        municipalities = self._create_municipalities()
        listings = self._create_listings(
            landlords, municipalities, num_listings,
        )
        self._create_queue_entries(listings, max_applicants)

        self.stdout.write(self.style.SUCCESS(
            f"Seeded {len(listings)} listings with queue entries."
        ))

    def _create_landlords(self) -> list[Landlord]:
        """Create or get the 10 major Swedish landlords."""
        landlords = []
        for name, org_nr in LANDLORDS:
            landlord, _ = Landlord.objects.get_or_create(
                org_number=org_nr,
                defaults={
                    "name": name,
                    "is_verified": random.random() > 0.2,
                    "website": f"https://www.{name.lower().replace(' ', '')}.se",
                },
            )
            landlords.append(landlord)
        self.stdout.write(f"  Landlords: {len(landlords)}")
        return landlords

    def _create_municipalities(self) -> dict[str, dict]:
        """Create municipalities and return mapping with districts."""
        result = {}
        for name, data in MUNICIPALITIES.items():
            muni, _ = Municipality.objects.get_or_create(
                name=name,
                defaults={"county": data["county"]},
            )
            result[name] = {"obj": muni, "districts": data["districts"]}
        self.stdout.write(f"  Municipalities: {len(result)}")
        return result

    def _create_listings(self, landlords, municipalities, count) -> list[Listing]:
        """Generate realistic rental listings."""
        today = timezone.localdate()
        listings = []
        muni_keys = list(municipalities.keys())

        for i in range(count):
            muni_name = random.choice(muni_keys)
            muni_data = municipalities[muni_name]
            district = random.choice(muni_data["districts"])
            rooms = random.choice(ROOM_WEIGHTS)

            # Size scales with rooms: base 20 + rooms * 15-22 sqm
            size = 20 + rooms * random.randint(15, 22) + random.randint(0, 10)

            # Rent formula from spec
            rent = 4500 + (rooms * 2200) + (size * 35) + random.randint(-800, 2000)
            rent = round(rent / 100) * 100  # Round to nearest 100

            street = f"{random.choice(STREETS)} {random.randint(1, 120)}"
            status = random.choice(STATUS_WEIGHTS)
            floor = random.randint(1, 8)
            total_floors = max(floor, random.randint(3, 10))

            listing = Listing.objects.create(
                landlord=random.choice(landlords),
                municipality=muni_data["obj"],
                street_address=street,
                district=district,
                postal_code=f"{random.randint(100, 199)} {random.randint(10, 99)}",
                city=muni_name if muni_name != "Stockholm" else "Stockholm",
                listing_type=random.choice([
                    Listing.ListingType.APARTMENT,
                    Listing.ListingType.APARTMENT,
                    Listing.ListingType.APARTMENT,
                    Listing.ListingType.ROOM,
                    Listing.ListingType.HOUSE,
                ]),
                rooms=rooms,
                size_sqm=size,
                floor=floor,
                total_floors=total_floors,
                has_elevator=random.random() > 0.4,
                has_balcony=random.random() > 0.3,
                has_parking=random.random() > 0.6,
                is_accessible=random.random() > 0.7,
                allows_pets=random.random() > 0.5,
                rent_sek=rent,
                min_income_multiplier=random.choice([2.5, 3.0, 3.0, 3.5]),
                max_household_size=random.choice([2, 4, 4, 6, 6, 8]),
                status=status,
                available_from=today + timedelta(days=random.randint(14, 90)),
                application_deadline=(
                    today + timedelta(days=random.randint(7, 30))
                    if random.random() > 0.3 else None
                ),
                title=f"{rooms} rum i {district}, {muni_name} — {size} kvm",
                description=(
                    f"Ljus och fräsch {rooms}-rumslägenhet i {district}. "
                    f"Nära till kollektivtrafik och service. "
                    f"Hyra {rent} kr/mån. Inflyttning möjlig från "
                    f"{(today + timedelta(days=random.randint(14, 90))).isoformat()}."
                ),
            )

            # Create queue config for this listing
            QueueConfig.objects.create(
                listing=listing,
                queue_type=random.choice(QUEUE_TYPE_WEIGHTS),
                require_bankid=random.random() > 0.15,
                require_no_debt=True,
                min_credit_score=random.choice([50.0, 55.0, 60.0, 65.0, 70.0]),
                min_queue_points=(
                    random.choice([None, None, 100, 200, 500])
                ),
            )

            listings.append(listing)

        self.stdout.write(f"  Listings: {len(listings)}")
        return listings

    def _create_queue_entries(self, listings, max_applicants):
        """Generate realistic applicant queue entries."""
        total = 0
        for listing in listings:
            num_applicants = random.randint(5, max_applicants)
            used_emails = set()

            for _ in range(num_applicants):
                first = random.choice(SWEDISH_FIRST_NAMES)
                last = random.choice(SWEDISH_LAST_NAMES)
                email = f"{first.lower()}.{last.lower()}@example.se"

                # Ensure unique email per listing
                if email in used_emails:
                    email = f"{first.lower()}.{last.lower()}{random.randint(1, 99)}@example.se"
                if email in used_emails:
                    continue
                used_emails.add(email)

                QueueEntry.objects.create(
                    listing=listing,
                    applicant_name=f"{first} {last}",
                    applicant_email=email,
                    monthly_income_sek=random.randint(22000, 85000),
                    household_size=random.choice([1, 1, 1, 2, 2, 3, 4]),
                    queue_points=random.randint(0, 5000),
                    bankid_verified=random.random() > 0.2,
                    credit_score=round(random.uniform(40, 100), 1),
                    has_debt_records=random.random() < 0.1,
                    preferred_districts=random.choice(
                        ["", ""]
                        + MUNICIPALITIES.get(
                            listing.municipality.name if listing.municipality else "Stockholm",
                            {"districts": [""]},
                        ).get("districts", [""])[:3]
                    ),
                )
                total += 1

        self.stdout.write(f"  Queue entries: {total}")
