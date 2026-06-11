"""
Tool: compute_birth_chart
Computes a natal (birth) chart using the Swiss Ephemeris via pyswisseph.

Returns:
  - Planetary positions (sign, degree, retrograde flag) for Sun through Pluto + Chiron + True Node
  - Whole-sign house cusps and Ascendant/MC
  - Chart metadata

The math comes entirely from the ephemeris; nothing is hallucinated.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

import swisseph as swe

from tools.geocode import geocode_place

logger = logging.getLogger(__name__)

# Planets we care about
_PLANETS = {
    swe.SUN:     "Sun",
    swe.MOON:    "Moon",
    swe.MERCURY: "Mercury",
    swe.VENUS:   "Venus",
    swe.MARS:    "Mars",
    swe.JUPITER: "Jupiter",
    swe.SATURN:  "Saturn",
    swe.URANUS:  "Uranus",
    swe.NEPTUNE: "Neptune",
    swe.PLUTO:   "Pluto",
    swe.CHIRON:  "Chiron",
    swe.TRUE_NODE: "North Node",
}

_SIGNS = [
    "Aries", "Taurus", "Gemini", "Cancer",
    "Leo", "Virgo", "Libra", "Scorpio",
    "Sagittarius", "Capricorn", "Aquarius", "Pisces",
]

_HOUSE_NAMES = [
    "", "1st", "2nd", "3rd", "4th", "5th", "6th",
    "7th", "8th", "9th", "10th", "11th", "12th",
]


def _degree_to_sign(lon: float) -> tuple[str, float]:
    """Convert ecliptic longitude to (sign, degree_within_sign)."""
    sign_index = int(lon / 30) % 12
    degree = lon % 30
    return _SIGNS[sign_index], round(degree, 4)


def _julian_day(year: int, month: int, day: int,
                hour: float, tz_offset: float) -> float:
    """Convert local datetime + UTC offset to Julian Day (UT)."""
    ut_hour = hour - tz_offset
    jd = swe.julday(year, month, day, ut_hour, swe.GREG_CAL)
    return jd


def _utc_offset_from_tz(tz_name: str, dt: datetime) -> float:
    """Return the UTC offset in decimal hours for the given timezone at dt."""
    try:
        import zoneinfo
        zone = zoneinfo.ZoneInfo(tz_name)
        aware = dt.replace(tzinfo=zone)
        offset_sec = aware.utcoffset().total_seconds()
        return offset_sec / 3600.0
    except Exception:
        return 0.0


def compute_birth_chart(
    date: str,
    time: str,
    place: str,
    house_system: str = "W",   # W = Whole Signs (traditional Jyotish/modern popular)
) -> dict:
    """
    Parameters
    ----------
    date  : ISO date string  "YYYY-MM-DD"
    time  : "HH:MM"  (24-hour local time; use "12:00" if unknown)
    place : Human-readable birth place, e.g. "New Delhi, India"
    house_system : single char for swe.houses(); default 'W' (Whole Sign)

    Returns a structured dict with planets, houses, and angles.
    """
    # ── Validate inputs ────────────────────────────────────────────────
    try:
        dt_date = datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        raise ValueError(f"Invalid date '{date}'. Use YYYY-MM-DD format.")

    try:
        h, m = [int(x) for x in time.split(":")]
        if not (0 <= h <= 23 and 0 <= m <= 59):
            raise ValueError()
    except Exception:
        raise ValueError(f"Invalid time '{time}'. Use HH:MM in 24-hour format.")

    year, month, day = dt_date.year, dt_date.month, dt_date.day

    # Reasonable birth year range
    if not (1800 <= year <= 2100):
        raise ValueError(f"Birth year {year} is outside the supported range (1800–2100).")

    # ── Geocode ─────────────────────────────────────────────────────────
    geo = geocode_place(place)
    lat, lon, tz_name = geo["latitude"], geo["longitude"], geo["timezone"]

    dt_local = datetime(year, month, day, h, m)
    tz_offset = _utc_offset_from_tz(tz_name, dt_local)

    local_decimal_hour = h + m / 60.0
    jd_ut = _julian_day(year, month, day, local_decimal_hour, tz_offset)

    # ── Planets ─────────────────────────────────────────────────────────
    swe.set_ephe_path(None)   # use built-in Moshier ephemeris
    planets = {}
    for planet_id, planet_name in _PLANETS.items():
        flags = swe.FLG_SPEED | swe.FLG_SWIEPH
        result, ret_flag = swe.calc_ut(jd_ut, planet_id, flags)
        longitude = result[0]
        speed = result[3]          # deg/day; negative = retrograde
        sign, deg_in_sign = _degree_to_sign(longitude)
        planets[planet_name] = {
            "longitude": round(longitude, 4),
            "sign": sign,
            "degree": deg_in_sign,
            "retrograde": speed < 0,
        }

    # ── Houses ──────────────────────────────────────────────────────────
    cusps, ascmc = swe.houses(jd_ut, lat, lon, house_system.encode())
    asc_lon = ascmc[0]
    mc_lon  = ascmc[1]

    asc_sign, asc_deg = _degree_to_sign(asc_lon)
    mc_sign, mc_deg   = _degree_to_sign(mc_lon)

    houses = {}
    for i, cusp in enumerate(cusps[1:], start=1):
        sign, deg = _degree_to_sign(cusp)
        houses[_HOUSE_NAMES[i]] = {
            "cusp_longitude": round(cusp, 4),
            "sign": sign,
            "degree": round(deg, 4),
        }

    # ── Assign planets to houses ────────────────────────────────────────
    def _house_of(lon: float) -> int:
        """Determine house number (whole-sign) for given ecliptic longitude."""
        asc_sign_idx = int(asc_lon / 30) % 12
        planet_sign_idx = int(lon / 30) % 12
        return ((planet_sign_idx - asc_sign_idx) % 12) + 1

    for pname, pdata in planets.items():
        pdata["house"] = _house_of(pdata["longitude"])

    return {
        "input": {
            "date": date,
            "time": time,
            "place": geo["place"],
            "latitude": lat,
            "longitude": lon,
            "timezone": tz_name,
            "utc_offset": tz_offset,
            "julian_day": round(jd_ut, 6),
            "house_system": "Whole Sign" if house_system == "W" else house_system,
        },
        "ascendant": {"sign": asc_sign, "degree": round(asc_deg, 4), "longitude": round(asc_lon, 4)},
        "midheaven": {"sign": mc_sign,  "degree": round(mc_deg, 4),  "longitude": round(mc_lon, 4)},
        "planets": planets,
        "houses": houses,
    }
