"""
Read-only lookups pang populate, plus barangay resolution/creation.

IMPORTANT: barangay names are NOT unique nationwide -- multiple cities/
regions can each have a barangay called "San Isidro", "Santo Domingo",
etc. 0001_create_barangays.sql only worked because every patient came
from Santa Rosa's 18 barangays. Now that nurse_intake.js sends a full
region -> city -> barangay PSGC cascade, anything resolving a barangay
MUST do it by barangay_code, never by name alone -- see
get_or_create_barangay() below and 0024_add_psgc_to_barangays.sql.

get_barangay_id() (name-only) is kept ONLY for the CSV import path,
where the spreadsheet has no code column. It is inherently ambiguous
once more than one region's barangays are loaded and should not be
used anywhere a barangay_code is available.
"""
from app.models.db import get_connection


def is_placeholder_barangay(name) -> bool:
    """Dropdown placeholder text ('Select City first', 'Select Barangay') that
    leaked in as if it were a real barangay name. Blank counts too."""
    n = (name or "").strip().casefold()
    return not n or n == "select" or n.startswith("select ")


def list_barangays() -> list[str]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT name FROM barangays WHERE LOWER(name) NOT LIKE 'select %' ORDER BY name"
    ).fetchall()
    conn.close()
    return [r["name"] for r in rows]


def list_conditions(category: str) -> list[str]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT code FROM condition_catalog WHERE category = ? ORDER BY id",
        (category,)
    ).fetchall()
    conn.close()
    return [r["code"] for r in rows]


def get_barangay_id(name: str) -> int | None:
    """
    Legacy name-only lookup. AMBIGUOUS once two loaded barangays share a
    name -- returns whichever row SQLite happens to match first. Only
    call this where no barangay_code is available (CSV import).
    """
    if not name:
        return None
    conn = get_connection()
    row = conn.execute(
        "SELECT id FROM barangays WHERE name = ?", (name,)
    ).fetchone()
    conn.close()
    return row["id"] if row else None


def get_barangay_id_by_code(barangay_code: str) -> int | None:
    """Unambiguous lookup by PSGC barangay code."""
    if not barangay_code:
        return None
    conn = get_connection()
    row = conn.execute(
        "SELECT id FROM barangays WHERE barangay_code = ?", (barangay_code,)
    ).fetchone()
    conn.close()
    return row["id"] if row else None


def get_or_create_barangay(
    barangay_code: str,
    name: str,
    city_code: str | None = None,
    city_name: str | None = None,
    region_code: str | None = None,
    region_name: str | None = None,
) -> int | None:
    """
    Resolve a barangay row by its PSGC code (authoritative), inserting it
    the first time this code is used. This is what nurse_intake.js's
    region/city/barangay cascade should be resolved through: it already
    sends barangay_code alongside barangay_name, so the backend does not
    need every barangay in the country pre-seeded -- rows are created on
    first use and reused (by code, not name) after that.
    """
    if not barangay_code or is_placeholder_barangay(name):
        return None
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT id FROM barangays WHERE barangay_code = ?", (barangay_code,)
        ).fetchone()
        if row:
            return row["id"]
        cur = conn.execute(
            """
            INSERT INTO barangays (barangay_code, name, city_code, city_name, region_code, region_name)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (barangay_code, name, city_code, city_name, region_code, region_name),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def get_or_create_barangay_by_name(name: str) -> int | None:
    """
    Best-effort fallback for the manual-barangay-entry case in
    nurse_intake.js (used when a city has no PSGC barangay list, so the
    nurse types a barangay in free text and no code is sent). Matches an
    existing row by name if one exists, otherwise creates a bare
    (codeless) row instead of rejecting the intake outright. Ambiguous by
    construction -- only call this when no barangay_code was provided.
    """
    if is_placeholder_barangay(name):
        return None
    conn = get_connection()
    try:
        row = conn.execute("SELECT id FROM barangays WHERE name = ?", (name,)).fetchone()
        if row:
            return row["id"]
        cur = conn.execute("INSERT INTO barangays (name) VALUES (?)", (name,))
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()



def get_barangay_name_by_id(barangay_id: int) -> str | None:
    """Display lookup -- used by user.py to show a staff member's linked
    barangay (users.barangay_id, added in 0026) instead of the legacy
    free-text slug."""
    if not barangay_id:
        return None
    conn = get_connection()
    row = conn.execute(
        "SELECT name FROM barangays WHERE id = ?", (barangay_id,)
    ).fetchone()
    conn.close()
    return row["name"] if row else None


# ---------------------------------------------------------------------------
# CSV import support: resolving free-text region/city/barangay names
# ---------------------------------------------------------------------------
# The CSV import template has no code column (a person filling a spreadsheet
# by hand can't be expected to know a PSGC code), only free-text region/
# city/barangay names. Matching barangay name alone is unsafe at national
# scale (600+ barangays are named "Poblacion"), so resolve_barangay_from_names
# below uses data/psgc_data.json itself to scope the match to the stated
# city (and region, if given) before accepting it -- collisions are far
# rarer once a barangay name is scoped to one specific city.

import json
import os
import threading

_psgc_cache = None
_psgc_lock = threading.Lock()


def _load_psgc_data():
    global _psgc_cache
    if _psgc_cache is not None:
        return _psgc_cache
    with _psgc_lock:
        if _psgc_cache is None:
            # this file lives at app/models/lookup_model.py; data/ sits at
            # the project root, two levels up.
            here = os.path.dirname(os.path.abspath(__file__))
            project_root = os.path.abspath(os.path.join(here, "..", ".."))
            path = os.path.join(project_root, "data", "psgc_data.json")
            with open(path, encoding="utf-8") as f:
                _psgc_cache = json.load(f)
    return _psgc_cache


def resolve_barangay_from_names(barangay_name, city_name=None, region_name=None):
    """
    Resolve the free-text region/city/barangay columns from a CSV import
    row to a barangay_id, using data/psgc_data.json to disambiguate --
    NOT a bare name match against the barangays table.

    Returns (barangay_id, warning): warning is None on a clean, unambiguous
    match; otherwise it explains what had to be guessed, for the caller to
    surface back to the person reviewing the import.
    """
    barangay_name = (barangay_name or "").strip()
    if not barangay_name:
        return None, None
    if is_placeholder_barangay(barangay_name):
        return None, f"barangay {barangay_name!r} is dropdown placeholder text -- left blank."

    city_name = (city_name or "").strip()
    region_name = (region_name or "").strip()

    if not city_name:
        bid = get_or_create_barangay_by_name(barangay_name)
        return bid, (
            f"no city given for barangay {barangay_name!r} -- matched/created "
            "by name alone, which is ambiguous nationwide (many barangays "
            "share a name). Add a city column value to resolve this safely."
        )

    try:
        psgc = _load_psgc_data()
    except (OSError, json.JSONDecodeError):
        bid = get_or_create_barangay_by_name(barangay_name)
        return bid, "could not load data/psgc_data.json -- matched/created by name alone."

    def _norm(s):
        return s.casefold().replace("city of ", "").strip()

    region_codes = None
    if region_name:
        region_codes = {
            r["code"] for r in psgc["regions"]
            if _norm(region_name) in _norm(r["name"]) or _norm(r["name"]) in _norm(region_name)
        }

    city_matches = [c for c in psgc["cities"] if _norm(c["name"]) == _norm(city_name)]
    if region_codes:
        scoped = [c for c in city_matches if c["regionCode"] in region_codes]
        if scoped:
            city_matches = scoped

    if not city_matches:
        bid = get_or_create_barangay_by_name(barangay_name)
        return bid, (
            f"city {city_name!r} not found in the PSGC dataset -- matched/created "
            f"barangay {barangay_name!r} by name alone."
        )

    for city in city_matches:
        brgy = next(
            (b for b in psgc["barangays"]
             if b["cityCode"] == city["code"] and b["name"].casefold() == barangay_name.casefold()),
            None,
        )
        if brgy:
            region = next((r for r in psgc["regions"] if r["code"] == city["regionCode"]), None)
            bid = get_or_create_barangay(
                brgy["code"], brgy["name"],
                city["code"], city["name"],
                city["regionCode"], region["name"] if region else region_name or None,
            )
            return bid, None

    bid = get_or_create_barangay_by_name(barangay_name)
    return bid, (
        f"barangay {barangay_name!r} not found under city {city_name!r} in the "
        "PSGC dataset -- matched/created by name alone."
    )


# ---------------------------------------------------------------------------
# Patient portal: region -> (province) -> city -> barangay address cascade
# ---------------------------------------------------------------------------
# Used when a patient relocates and updates their own address. The browser only
# ever sends PSGC *codes*; names and the barangay row come from the server's own
# data/psgc_data.json, so a tampered form can't invent or mislabel a location.
#
# The dataset is indexed once into hash maps (code -> row, parent code -> rows)
# so every lookup is O(1) instead of scanning tens of thousands of barangays on
# each request.
#
# Province is optional: patients only get a province step if the dataset has
# a "provinces" list and cities carry a "provinceCode". The barangays table
# stores region/city/barangay but not province, so province narrows the
# dropdowns and is validated, but is not saved on its own.

LOCATION_LEVELS = ("region", "province", "city", "barangay")

_psgc_index = None
_psgc_index_lock = threading.Lock()


def _build_psgc_index():
    global _psgc_index
    if _psgc_index is not None:
        return _psgc_index
    with _psgc_index_lock:
        if _psgc_index is None:
            data = _load_psgc_data()
            provinces = data.get("provinces") or []
            has_provinces = bool(provinces) and any(c.get("provinceCode") for c in data["cities"])
            idx = {
                "has_provinces": has_provinces,
                "region": {r["code"]: r for r in data["regions"]},
                "province": {p["code"]: p for p in provinces},
                "city": {c["code"]: c for c in data["cities"]},
                "barangay": {b["code"]: b for b in data["barangays"]},
                "provinces_by_region": {},
                "cities_by_region": {},
                "cities_by_province": {},
                "barangays_by_city": {},
            }
            for p in provinces:
                idx["provinces_by_region"].setdefault(p.get("regionCode"), []).append(p)
            for c in data["cities"]:
                idx["cities_by_region"].setdefault(c.get("regionCode"), []).append(c)
                if c.get("provinceCode"):
                    idx["cities_by_province"].setdefault(c["provinceCode"], []).append(c)
            for b in data["barangays"]:
                idx["barangays_by_city"].setdefault(b.get("cityCode"), []).append(b)
            _psgc_index = idx
    return _psgc_index


def psgc_has_provinces() -> bool:
    try:
        return _build_psgc_index()["has_provinces"]
    except (OSError, json.JSONDecodeError):
        return False


def psgc_location_options(level: str, parent_code: str | None = None) -> list[dict]:
    """[{code, name}] sorted by name for one dropdown of the address cascade.
    region: no parent. province: parent = region code. city: parent = province
    code (when the dataset has provinces) or region code. barangay: parent = city code."""
    if level not in LOCATION_LEVELS:
        raise ValueError("Unknown location level.")
    idx = _build_psgc_index()
    if level == "region":
        rows = idx["region"].values()
    elif level == "province":
        rows = idx["provinces_by_region"].get(parent_code, []) if idx["has_provinces"] else []
    elif level == "city":
        if idx["has_provinces"] and parent_code in idx["province"]:
            rows = idx["cities_by_province"].get(parent_code, [])
        else:
            rows = idx["cities_by_region"].get(parent_code, [])
    else:
        rows = idx["barangays_by_city"].get(parent_code, [])
    return sorted(({"code": r["code"], "name": r["name"]} for r in rows),
                  key=lambda r: r["name"].casefold())


def resolve_psgc_location(region_code, city_code, barangay_code, province_code=None):
    """
    Validate a submitted region/(province)/city/barangay chain against the PSGC
    dataset and return (barangay_id, None), or (None, "reason") if any link is
    unknown or doesn't belong to its parent.
    """
    try:
        idx = _build_psgc_index()
    except (OSError, json.JSONDecodeError):
        return None, "Address options are unavailable right now. Please try again later."

    region = idx["region"].get(region_code)
    city = idx["city"].get(city_code)
    brgy = idx["barangay"].get(barangay_code)
    if not (region and city and brgy):
        return None, "Please choose a region, city and barangay from the lists."
    if city.get("regionCode") != region["code"]:
        return None, "That city is not in the selected region."
    if brgy.get("cityCode") != city["code"]:
        return None, "That barangay is not in the selected city."
    if province_code and idx["has_provinces"]:
        if province_code not in idx["province"] or city.get("provinceCode") != province_code:
            return None, "That city is not in the selected province."

    barangay_id = get_or_create_barangay(
        brgy["code"], brgy["name"], city["code"], city["name"], region["code"], region["name"]
    )
    if barangay_id is None:
        return None, "That barangay could not be saved."
    return barangay_id, None