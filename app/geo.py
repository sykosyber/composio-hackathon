"""Offline coarse geocoding for San Francisco.

No network call, so a pin always gets a human readable location even with everything down.
Returns a neighborhood plus the nearest known intersection in the demo area.
"""
from __future__ import annotations

from math import cos, radians, sqrt

# (name, lat, lng). Mission-heavy, since the demo clusters there.
LANDMARKS: list[tuple[str, float, float]] = [
    ("Valencia St and 18th St", 37.76150, -122.42180),
    ("Valencia St and 16th St", 37.76503, -122.42194),
    ("Valencia St and 24th St", 37.75234, -122.42062),
    ("Mission St and 16th St", 37.76500, -122.41966),
    ("Mission St and 24th St", 37.75222, -122.41834),
    ("Guerrero St and 20th St", 37.75824, -122.42393),
    ("Dolores St and 18th St", 37.76117, -122.42623),
    ("Folsom St and 22nd St", 37.75540, -122.41296),
    ("Potrero Ave and 20th St", 37.75850, -122.40720),
    ("Harrison St and 19th St", 37.76030, -122.41280),
    ("Bryant St and 17th St", 37.76330, -122.41060),
    ("Church St and Market St", 37.76730, -122.42900),
    ("Castro St and 18th St", 37.76100, -122.43500),
    ("Haight St and Ashbury St", 37.77000, -122.44640),
    ("Embarcadero and Market St", 37.79380, -122.39540),
    ("Powell St and Market St", 37.78480, -122.40770),
]

NEIGHBORHOODS: list[tuple[str, float, float, float]] = [
    # name, lat, lng, radius in km
    ("the Mission", 37.7599, -122.4148, 1.6),
    ("the Castro", 37.7609, -122.4350, 1.0),
    ("Noe Valley", 37.7502, -122.4337, 1.0),
    ("Potrero Hill", 37.7576, -122.4011, 1.2),
    ("SoMa", 37.7785, -122.4056, 1.4),
    ("Hayes Valley", 37.7765, -122.4241, 0.9),
    ("the Haight", 37.7700, -122.4464, 1.2),
    ("downtown San Francisco", 37.7879, -122.4075, 1.2),
]


def km_between(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Equirectangular approximation. Plenty accurate across a few city blocks."""
    x = radians(lng2 - lng1) * cos(radians((lat1 + lat2) / 2))
    y = radians(lat2 - lat1)
    return 6371.0 * sqrt(x * x + y * y)


def neighborhood(lat: float, lng: float) -> str:
    best, best_km = "", 1e9
    for name, nlat, nlng, radius in NEIGHBORHOODS:
        d = km_between(lat, lng, nlat, nlng)
        if d <= radius and d < best_km:
            best, best_km = name, d
    return best or "San Francisco"


def address_hint(lat: float, lng: float) -> str:
    """Nearest named intersection when close, otherwise the neighborhood."""
    name, dist = "", 1e9
    for label, llat, llng in LANDMARKS:
        d = km_between(lat, lng, llat, llng)
        if d < dist:
            name, dist = label, d
    if dist <= 0.18:
        return name
    if dist <= 0.5:
        return f"near {name}"
    return neighborhood(lat, lng)
