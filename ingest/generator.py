"""
Synthetic CDR generator for the telecom analytics demo.

SYNTHETIC DATA ONLY — nothing here touches real subscribers. The functions in
this module are deliberately pure (they build and return Python objects and do
no I/O) so they can be unit-tested / verified against any ClickHouse engine.
The actual dual-write to ClickHouse + Memgraph lives in writers.py / main.py.

Design notes
------------
* ~2000 subscribers, ~500k calls by default (configurable).
* Coordinates cluster around real Ethiopian cities so the map looks real.
* Each subscriber has a small "contact list"; calls are drawn from it, which
  gives the Memgraph contact network realistic clustering for depth 1-2 queries.
* A handful of devices are deliberately *shared* by 2-3 subscribers so the
  shared-device detection query has something to find.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Iterator

from faker import Faker

# ---------------------------------------------------------------------------
# Reference data
# ---------------------------------------------------------------------------

# (name, center_lat, center_lon) for real Ethiopian cities. Cells/calls jitter
# around these centers so the Leaflet map shows believable clusters.
CITIES = [
    ("Addis Ababa", 9.0300, 38.7400),
    ("Dire Dawa", 9.5930, 41.8660),
    ("Bahir Dar", 11.5936, 37.3908),
    ("Mekelle", 13.4969, 39.4769),
    ("Hawassa", 7.0622, 38.4777),
]

OPERATORS = ["Safaricom", "Ethio Telecom"]

# MCC 636 = Ethiopia. MNC differs per operator (synthetic but plausible).
OPERATOR_MNC = {"Ethio Telecom": "01", "Safaricom": "03"}
# National mobile prefix after country code 251: 9 (Ethio Telecom), 7 (Safaricom).
OPERATOR_MSISDN_PREFIX = {"Ethio Telecom": "9", "Safaricom": "7"}

DEVICE_MODELS = [
    "Samsung Galaxy A14", "Samsung Galaxy A54", "Tecno Spark 10",
    "Tecno Camon 20", "Infinix Hot 30", "Infinix Note 30",
    "itel A60", "Xiaomi Redmi 12", "Nokia G21", "Huawei nova 11",
    "iPhone 13", "iPhone 15", "Oppo A78", "Realme C55",
]

CALL_TYPES = ["voice", "sms", "data", "video"]
CALL_TYPE_WEIGHTS = [0.55, 0.25, 0.15, 0.05]

CALL_RESULTS = ["answered", "missed", "busy", "failed"]
CALL_RESULT_WEIGHTS = [0.78, 0.12, 0.06, 0.04]

NETWORK_TYPES = ["2G", "3G", "4G", "5G"]
NETWORK_TYPE_WEIGHTS = [0.05, 0.20, 0.65, 0.10]

ETHIOPIAN_FIRST = [
    "Abebe", "Almaz", "Bekele", "Chala", "Dawit", "Eyob", "Feven", "Genet",
    "Hanna", "Iskinder", "Kebede", "Lemlem", "Meron", "Nardos", "Samuel",
    "Tigist", "Yonas", "Zere", "Selam", "Biruk", "Hiwot", "Mulugeta",
    "Rahel", "Tariku", "Wubishet", "Yohannes", "Aster", "Girma", "Liya",
]
ETHIOPIAN_LAST = [
    "Bekele", "Tadesse", "Alemu", "Girma", "Haile", "Kassa", "Mengistu",
    "Tesfaye", "Wolde", "Desta", "Gebre", "Assefa", "Demeke", "Tola",
    "Abera", "Negash", "Solomon", "Fikru", "Mekonnen", "Lemma",
]


# ---------------------------------------------------------------------------
# Domain objects
# ---------------------------------------------------------------------------

@dataclass
class Cell:
    cell_id: str
    lac_tac: str
    latitude: float
    longitude: float
    location_name: str


@dataclass
class Device:
    imei: str
    model: str


@dataclass
class Subscriber:
    number: str
    name: str
    imsi: str
    operator: str
    reg_date: date
    device: Device
    home_city: str
    contacts: list[str] = field(default_factory=list)
    behavior: str = "normal"  # normal | burner | night


# CDR column order — must match the INSERT column list (warrant_id omitted so it
# uses its DEFAULT '' seam).
CDR_COLUMNS = [
    "record_id", "caller_number", "callee_number", "subscriber_name", "imsi",
    "imei", "device_model", "operator", "call_type", "direction", "call_start",
    "call_end", "duration_sec", "call_result", "cell_id", "lac_tac",
    "latitude", "longitude", "location_name", "roaming_flag", "network_type",
    "registration_date", "charge_amount", "data_volume_mb", "ingest_timestamp",
]


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------

def _rng(seed: int | None) -> random.Random:
    return random.Random(seed)


def _faker(seed: int | None) -> Faker:
    """A seeded Faker instance — used for reproducible UUIDs / record ids."""
    fake = Faker()
    if seed is not None:
        Faker.seed(seed)
    return fake


def build_cells(rng: random.Random, cells_per_city: int = 6) -> list[Cell]:
    """A handful of cell towers jittered around each city center."""
    cells: list[Cell] = []
    for city, lat, lon in CITIES:
        for i in range(cells_per_city):
            cells.append(
                Cell(
                    cell_id=f"{city[:3].upper()}-{rng.randint(10000, 99999)}",
                    lac_tac=f"LAC-{rng.randint(100, 999)}",
                    latitude=round(lat + rng.uniform(-0.06, 0.06), 6),
                    longitude=round(lon + rng.uniform(-0.06, 0.06), 6),
                    location_name=city,
                )
            )
    return cells


def _msisdn(rng: random.Random, operator: str) -> str:
    prefix = OPERATOR_MSISDN_PREFIX[operator]
    return "251" + prefix + "".join(str(rng.randint(0, 9)) for _ in range(8))


def _imsi(rng: random.Random, operator: str) -> str:
    return "636" + OPERATOR_MNC[operator] + "".join(
        str(rng.randint(0, 9)) for _ in range(10)
    )


def _imei(rng: random.Random) -> str:
    return "".join(str(rng.randint(0, 9)) for _ in range(15))


def build_subscribers(
    rng: random.Random,
    n_subscribers: int,
    shared_device_groups: int = 25,
    n_burners: int = 15,
    n_night_owls: int = 20,
) -> list[Subscriber]:
    """Create subscribers, each with a device, and inject some shared devices."""
    subs: list[Subscriber] = []
    seen_numbers: set[str] = set()
    today = date(2026, 6, 18)

    for _ in range(n_subscribers):
        operator = rng.choice(OPERATORS)
        number = _msisdn(rng, operator)
        while number in seen_numbers:
            number = _msisdn(rng, operator)
        seen_numbers.add(number)

        subs.append(
            Subscriber(
                number=number,
                name=f"{rng.choice(ETHIOPIAN_FIRST)} {rng.choice(ETHIOPIAN_LAST)}",
                imsi=_imsi(rng, operator),
                operator=operator,
                reg_date=today - timedelta(days=rng.randint(30, 365 * 5)),
                device=Device(imei=_imei(rng), model=rng.choice(DEVICE_MODELS)),
                home_city=rng.choice(CITIES)[0],
                contacts=[],
            )
        )

    # Inject shared devices: pick small groups and give them one shared IMEI.
    # This is the signal the shared-device detection query surfaces.
    if len(subs) >= 3:
        for _ in range(shared_device_groups):
            group = rng.sample(subs, rng.randint(2, 3))
            shared = Device(imei=_imei(rng), model=rng.choice(DEVICE_MODELS))
            for s in group:
                s.device = shared

    # Inject suspicious behaviors so the detection queries have real signal.
    # (Like the shared-device injection above — synthetic data should contain
    # the patterns the tool is meant to surface.) Assigned BEFORE building
    # contact lists so burners can be kept out of everyone else's network and
    # stay genuinely low-volume.
    pool = list(subs)
    rng.shuffle(pool)
    burners = pool[:n_burners]
    night_owls = pool[n_burners:n_burners + n_night_owls]
    burner_set = {s.number for s in burners}
    for s in burners:
        s.behavior = "burner"
    for s in night_owls:
        s.behavior = "night"

    # Candidates that may appear in others' contact lists (everyone but burners).
    contactable = [s for s in subs if s.number not in burner_set]

    # Build a contact list per subscriber (their personal call network).
    for s in subs:
        if s.behavior == "burner":
            # very few contacts (drawn from non-burners)
            s.contacts = [rng.choice(contactable).number for _ in range(rng.randint(1, 3))]
            continue
        n_contacts = rng.randint(5, 30)
        contacts = set()
        while len(contacts) < min(n_contacts, len(contactable) - 1):
            other = rng.choice(contactable)
            if other.number != s.number:
                contacts.add(other.number)
        s.contacts = list(contacts)

    return subs


def generate_cdrs(
    rng: random.Random,
    fake: Faker,
    subscribers: list[Subscriber],
    cells: list[Cell],
    n_calls: int,
    start_date: datetime,
    end_date: datetime,
) -> Iterator[tuple]:
    """
    Yield CDR rows as tuples ordered like CDR_COLUMNS.

    Most calls: a caller picks one of their contacts (90%) or a random number
    (10%), at a cell near the caller's home city (with occasional roaming).
    Burner and night-owl subscribers get dedicated call patterns so the
    suspicious-pattern detection has real signal.
    """
    cells_by_city: dict[str, list[Cell]] = {}
    for c in cells:
        cells_by_city.setdefault(c.location_name, []).append(c)

    span_sec = int((end_date - start_date).total_seconds())
    now = datetime(2026, 6, 18, 12, 0, 0)

    normal = [s for s in subscribers if s.behavior == "normal"]
    burners = [s for s in subscribers if s.behavior == "burner"]
    night_owls = [s for s in subscribers if s.behavior == "night"]

    emitted = 0

    # --- burners: short-lived, few outgoing calls in a tight time window ---
    for b in burners:
        if not b.contacts:
            continue
        window_start = rng.randint(0, max(1, span_sec - 7 * 86400))
        window_len = rng.randint(2 * 86400, 7 * 86400)
        for _ in range(rng.randint(5, 20)):
            cs = start_date + timedelta(seconds=window_start + rng.randint(0, window_len))
            yield _make_row(rng, fake, b, rng.choice(b.contacts), cells_by_city,
                            cs, now, direction="outgoing")
            emitted += 1

    # --- night owls: activity concentrated between 00:00 and 05:00 ---
    for s in night_owls:
        targets = s.contacts or [rng.choice(normal).number]
        for _ in range(rng.randint(25, 60)):
            day = start_date + timedelta(seconds=rng.randint(0, span_sec))
            cs = day.replace(hour=rng.randint(0, 4), minute=rng.randint(0, 59),
                             second=rng.randint(0, 59), microsecond=0)
            yield _make_row(rng, fake, s, rng.choice(targets), cells_by_city, cs, now)
            emitted += 1

    # --- normal traffic fills the remaining budget ---
    pool = normal if normal else subscribers
    while emitted < n_calls:
        caller = rng.choice(pool)
        if caller.contacts and rng.random() < 0.90:
            callee_number = rng.choice(caller.contacts)
        else:
            callee_number = rng.choice(pool).number
            if callee_number == caller.number:
                continue
        cs = start_date + timedelta(seconds=rng.randint(0, span_sec))
        yield _make_row(rng, fake, caller, callee_number, cells_by_city, cs, now)
        emitted += 1


def _make_row(rng, fake, caller, callee_number, cells_by_city, call_start, now,
              direction=None):
    """Build one CDR tuple (ordered like CDR_COLUMNS) for a given caller/callee
    and start time."""
    call_type = rng.choices(CALL_TYPES, CALL_TYPE_WEIGHTS)[0]
    if direction is None:
        direction = rng.choice(["outgoing", "incoming"])
    result = rng.choices(CALL_RESULTS, CALL_RESULT_WEIGHTS)[0]

    if result == "answered":
        if call_type == "sms":
            duration = 0
        elif call_type == "data":
            duration = rng.randint(10, 3600)
        else:
            duration = rng.randint(5, 1800)
    else:
        duration = 0

    call_end = call_start + timedelta(seconds=duration)

    # The call connects at a fixed cell tower, so the CDR carries that tower's
    # coordinates — this keeps the location rollup genuinely pre-aggregated.
    roaming = rng.random() < 0.08
    city = rng.choice(CITIES)[0] if roaming else caller.home_city
    cell = rng.choice(cells_by_city.get(city, [c for cs in cells_by_city.values() for c in cs]))

    data_volume = round(rng.uniform(0.1, 500.0), 2) if call_type == "data" else 0.0

    if call_type == "sms":
        charge = Decimal("0.5000")
    elif call_type == "data":
        charge = Decimal(str(round(data_volume * 0.05, 4)))
    else:
        charge = Decimal(str(round(duration / 60.0 * 0.83, 4)))

    return (
        fake.uuid4(),
        caller.number,
        callee_number,
        caller.name,
        caller.imsi,
        caller.device.imei,
        caller.device.model,
        caller.operator,
        call_type,
        direction,
        call_start,
        call_end,
        duration,
        result,
        cell.cell_id,
        cell.lac_tac,
        cell.latitude,
        cell.longitude,
        cell.location_name,
        1 if roaming else 0,
        rng.choices(NETWORK_TYPES, NETWORK_TYPE_WEIGHTS)[0],
        caller.reg_date,
        charge,
        data_volume,
        now,
    )
