"""
Tool: get_daily_transits
Fetches current (or given-date) planetary positions and relates them
to the user's natal chart by computing aspects.

Aspect orbs used:
  Conjunction  0°  ± 8°
  Opposition 180°  ± 8°
  Trine      120°  ± 6°
  Square      90°  ± 6°
  Sextile     60°  ± 4°
"""
from __future__ import annotations

import logging
from datetime import date as DateType, datetime

import swisseph as swe

from tools.birth_chart import _PLANETS, _SIGNS, _degree_to_sign

logger = logging.getLogger(__name__)

_ASPECTS = [
    ("Conjunction",  0,   8),
    ("Opposition",  180,  8),
    ("Trine",       120,  6),
    ("Square",       90,  6),
    ("Sextile",      60,  4),
]


def _angular_distance(a: float, b: float) -> float:
    diff = abs(a - b) % 360
    return diff if diff <= 180 else 360 - diff


def _check_aspect(transit_lon: float, natal_lon: float) -> dict | None:
    for name, angle, orb in _ASPECTS:
        if abs(_angular_distance(transit_lon, natal_lon) - angle) <= orb:
            exact_orb = abs(_angular_distance(transit_lon, natal_lon) - angle)
            return {"aspect": name, "orb": round(exact_orb, 2)}
    return None


def get_daily_transits(
    query_date: str | None = None,
    natal_chart: dict | None = None,
) -> dict:
    """
    Parameters
    ----------
    query_date  : ISO date string "YYYY-MM-DD"; defaults to today (UTC)
    natal_chart : The output of compute_birth_chart(); if provided,
                  aspects between transit planets and natal planets are included.

    Returns current planetary positions and (optionally) natal aspects.
    """
    if query_date is None:
        query_date = DateType.today().isoformat()

    try:
        dt = datetime.strptime(query_date, "%Y-%m-%d")
    except ValueError:
        raise ValueError(f"Invalid date '{query_date}'. Use YYYY-MM-DD.")

    # Use noon UTC as reference time for the day
    jd_ut = swe.julday(dt.year, dt.month, dt.day, 12.0)

    transit_positions: dict[str, dict] = {}
    for planet_id, planet_name in _PLANETS.items():
        flags = swe.FLG_SPEED | swe.FLG_SWIEPH
        result, _ = swe.calc_ut(jd_ut, planet_id, flags)
        lon = result[0]
        speed = result[3]
        sign, deg = _degree_to_sign(lon)
        transit_positions[planet_name] = {
            "longitude": round(lon, 4),
            "sign": sign,
            "degree": deg,
            "retrograde": speed < 0,
        }

    # ── Aspects to natal chart ──────────────────────────────────────────
    aspects = []
    if natal_chart and "planets" in natal_chart:
        natal_planets = natal_chart["planets"]
        for t_name, t_data in transit_positions.items():
            for n_name, n_data in natal_planets.items():
                aspect_info = _check_aspect(t_data["longitude"], n_data["longitude"])
                if aspect_info:
                    aspects.append({
                        "transit_planet": t_name,
                        "natal_planet": n_name,
                        "aspect": aspect_info["aspect"],
                        "orb": aspect_info["orb"],
                    })

    # Sort aspects by tightness
    aspects.sort(key=lambda x: x["orb"])

    return {
        "date": query_date,
        "transit_positions": transit_positions,
        "natal_aspects": aspects,
        "has_natal_chart": natal_chart is not None,
    }
