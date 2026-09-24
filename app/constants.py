"""Shared account-management display values."""

BARANGAYS = [
    ("aplaya", "Aplaya"),
    ("balibago", "Balibago"),
    ("caingin", "Caingin"),
    ("dila", "Dila"),
    ("dita", "Dita"),
    ("don_jose", "Don Jose"),
    ("ibaba", "Ibaba"),
    ("kanluran", "Kanluran (Poblacion Uno)"),
    ("labas", "Labas"),
    ("macabling", "Macabling"),
    ("malitlit", "Malitlit"),
    ("malusak", "Malusak (Poblacion Dos)"),
    ("market_area", "Market Area (Poblacion Tres)"),
    ("pooc", "Pooc"),
    ("pulong_santa_cruz", "Pulong Santa Cruz"),
    ("santo_domingo", "Santo Domingo"),
    ("sinalhan", "Sinalhan"),
    ("tagapo", "Tagapo"),
]

ROLE_MAP = {
    "Health Officer": "medical_officer",
    "LHU Nurse": "health_worker",
}

STATION_MAP = {
    "LHU I": "lhui",
    "LHU II": "lhuii",
}

CSV_IMPORT_COLUMNS = [
    "first_name",
    "middle_name",
    "last_name",
    "birthday",
    "sex",
    "email",
    "phone",
    "role",
    "station",
    "barangay",
    "temporary_password",
]
