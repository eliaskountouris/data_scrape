"""common.weather -- weather, sunrise and sunset for any coordinate.

    from common.weather import Location, OpenMeteoDaily, OpenMeteoHourly

    nyc = Location(40.7128, -74.0060, "NYC")
    days = OpenMeteoDaily().load_range(nyc, "2025-01-01", "2025-12-31")
    hours = OpenMeteoHourly().load_range([nyc, (51.5, -0.13)], "2025-06-01", "2025-06-07")

Daily rows carry sunrise/sunset/day length alongside the weather; hourly rows
carry an ``is_day`` flag. Backed by Open-Meteo (free, no key).
"""

from .openmeteo import WMO_CODES, Location, OpenMeteoDaily, OpenMeteoHourly
from .schema import DailyWeatherSchema, HourlyWeatherSchema

__all__ = [
    "Location",
    "OpenMeteoDaily",
    "OpenMeteoHourly",
    "DailyWeatherSchema",
    "HourlyWeatherSchema",
    "WMO_CODES",
]
