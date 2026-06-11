"""
Tool: geocode_place
Resolves a human-readable place name to latitude, longitude, and IANA timezone.
Uses Nominatim (OpenStreetMap) — no API key required.
"""
from __future__ import annotations

import logging
from functools import lru_cache
from typing import Optional

from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderServiceError
from timezonefinder import TimezoneFinder

logger = logging.getLogger(__name__)

_geolocator = Nominatim(user_agent="aradhana-astroagent/1.0")
_tf = TimezoneFinder()


@lru_cache(maxsize=512)
def geocode_place(place: str) -> dict:
    """
    Given a place name string, return:
      { "place": str, "latitude": float, "longitude": float, "timezone": str }

    Raises ValueError on failure so the agent can handle it gracefully.
    """
    if not place or not place.strip():
        raise ValueError("Place name must not be empty.")

    place = place.strip()

    try:
        location = _geolocator.geocode(place, timeout=10)
    except GeocoderTimedOut:
        raise ValueError(f"Geocoding timed out for '{place}'. Try a more specific name.")
    except GeocoderServiceError as exc:
        raise ValueError(f"Geocoding service error: {exc}")

    if location is None:
        raise ValueError(
            f"Could not geocode '{place}'. "
            "Try including a country or region (e.g. 'Mumbai, India')."
        )

    lat, lon = location.latitude, location.longitude
    tz = _tf.timezone_at(lat=lat, lng=lon)

    if tz is None:
        # Ocean or unmapped area — fall back to UTC-offset estimate
        tz = "UTC"
        logger.warning("TimezoneFinder returned None for %.4f, %.4f; using UTC", lat, lon)

    return {
        "place": location.address,
        "latitude": round(lat, 6),
        "longitude": round(lon, 6),
        "timezone": tz,
    }
