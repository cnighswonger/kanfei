"""
Catalog of Historic Severe Weather Events for Temporal Tracking Validation

Each event includes:
- Location (lat/lon)
- Time of closest approach or peak intensity
- Event type and intensity
- Expected CWOP station coverage
"""

from datetime import datetime, timezone
from dataclasses import dataclass
from typing import Optional


@dataclass
class HistoricEvent:
    """Historic severe weather event metadata."""
    name: str
    event_type: str  # 'tornado', 'severe_thunderstorm', 'derecho'
    date: datetime
    closest_approach: datetime  # When system closest to test location
    latitude: float
    longitude: float
    intensity: str  # EF-scale for tornadoes, descriptive for others
    description: str
    cwop_region: str  # Expected CWOP coverage quality
    radar_station: str = "KTLX"  # NEXRAD radar station (default Oklahoma City)
    freezing_level_m: float = 4000  # Approximate 0°C isotherm height (meters AGL)

    # For temporal window calculation
    approach_duration_min: int = 80  # Minutes before closest approach
    departure_duration_min: int = 10  # Minutes after closest approach


# ============================================================================
# TORNADO EVENTS
# ============================================================================

MOORE_2013 = HistoricEvent(
    name="Moore EF5 Tornado",
    event_type="tornado",
    date=datetime(2013, 5, 20, tzinfo=timezone.utc),
    closest_approach=datetime(2013, 5, 20, 19, 56, tzinfo=timezone.utc),  # Tornado touchdown at Moore (T-0 = overhead)
    latitude=35.3396,
    longitude=-97.4867,
    intensity="EF5",
    description="Violent tornado through Moore, OK. 24 fatalities, $2B damage. Peak winds 210+ mph. NWS WARNING issued at 18:10 UTC (106 min lead time).",
    cwop_region="Oklahoma (excellent coverage)",
    approach_duration_min=120,  # 2hr before touchdown (17:56 baseline start)
    departure_duration_min=120,  # Through 21:56 to capture aftermath
)

EL_RENO_2013 = HistoricEvent(
    name="El Reno EF3 Tornado",
    event_type="tornado",
    date=datetime(2013, 5, 31, tzinfo=timezone.utc),
    closest_approach=datetime(2013, 5, 31, 23, 0, tzinfo=timezone.utc),  # ~6:00 PM local
    latitude=35.5331,
    longitude=-97.9506,
    intensity="EF3 (widest on record: 2.6 mi)",
    description="Widest tornado on record. Killed 8 including storm chasers. Rapid expansion.",
    cwop_region="Oklahoma (excellent coverage)",
    approach_duration_min=80,
    departure_duration_min=10,
)

JOPLIN_2011 = HistoricEvent(
    name="Joplin EF5 Tornado",
    event_type="tornado",
    date=datetime(2011, 5, 22, tzinfo=timezone.utc),
    closest_approach=datetime(2011, 5, 22, 22, 40, tzinfo=timezone.utc),  # ~5:40 PM local
    latitude=37.0842,
    longitude=-94.5133,
    intensity="EF5",
    description="Deadliest tornado since 1950. 161 fatalities, $2.8B damage. Through Joplin city center.",
    cwop_region="Missouri/Kansas border (good coverage)",
    approach_duration_min=80,
    departure_duration_min=10,
)

TUSCALOOSA_2011 = HistoricEvent(
    name="Tuscaloosa EF4 Tornado",
    event_type="tornado",
    date=datetime(2011, 4, 27, tzinfo=timezone.utc),
    closest_approach=datetime(2011, 4, 27, 22, 10, tzinfo=timezone.utc),  # ~5:10 PM local
    latitude=33.2098,
    longitude=-87.5692,
    intensity="EF4",
    description="Long-track tornado through Tuscaloosa, AL. 64 fatalities. Part of 2011 Super Outbreak.",
    cwop_region="Alabama (moderate coverage)",
    approach_duration_min=80,
    departure_duration_min=10,
)

PILGER_2014 = HistoricEvent(
    name="Pilger Twin EF4 Tornadoes",
    event_type="tornado",
    date=datetime(2014, 6, 16, tzinfo=timezone.utc),
    closest_approach=datetime(2014, 6, 16, 21, 0, tzinfo=timezone.utc),  # ~4:00 PM local
    latitude=42.0094,
    longitude=-97.0542,
    intensity="EF4 (twin tornadoes)",
    description="Rare twin tornadoes. Destroyed 50%+ of Pilger, NE. 2 fatalities.",
    cwop_region="Nebraska (good coverage)",
    radar_station="KOAX",  # Omaha, NE - closest NEXRAD to Pilger
    approach_duration_min=80,
    departure_duration_min=10,
)

# ============================================================================
# SEVERE THUNDERSTORM EVENTS (Non-tornadic)
# ============================================================================

OKLAHOMA_DERECHO_2012 = HistoricEvent(
    name="Oklahoma Derecho",
    event_type="derecho",
    date=datetime(2012, 6, 22, tzinfo=timezone.utc),
    closest_approach=datetime(2012, 6, 22, 20, 0, tzinfo=timezone.utc),
    latitude=35.4676,
    longitude=-97.5164,  # Oklahoma City
    intensity="80+ mph winds",
    description="Widespread damaging winds across Oklahoma. No tornado, but extensive wind damage.",
    cwop_region="Oklahoma (excellent coverage)",
    approach_duration_min=60,
    departure_duration_min=20,
)

GIANT_HAIL_2021 = HistoricEvent(
    name="Giant Hail San Antonio",
    event_type="severe_thunderstorm",
    date=datetime(2021, 4, 28, tzinfo=timezone.utc),
    closest_approach=datetime(2021, 4, 28, 22, 30, tzinfo=timezone.utc),
    latitude=29.4241,
    longitude=-98.4936,  # San Antonio
    intensity='6.4" hail (TX state record)',
    description="Record-setting hail event. 6.4 inch hailstone at Hondo. 2-4 inch hail across N Bexar County.",
    cwop_region="Texas (excellent coverage)",
    radar_station="KEWX",
    freezing_level_m=4200,
    approach_duration_min=60,
    departure_duration_min=30,
)

NEWNAN_2021 = HistoricEvent(
    name="Newnan EF4 Tornado",
    event_type="tornado",
    date=datetime(2021, 3, 26, tzinfo=timezone.utc),
    closest_approach=datetime(2021, 3, 26, 4, 6, tzinfo=timezone.utc),
    latitude=33.3807,
    longitude=-84.7997,
    intensity="EF4 (nocturnal, 170 mph)",
    description="Violent nocturnal EF4, 39-mile path. 1,700 homes damaged. KFFC radar ~20 km away.",
    cwop_region="Georgia/Atlanta metro (moderate-good coverage)",
    radar_station="KFFC",
    freezing_level_m=3200,
    approach_duration_min=90,
    departure_duration_min=30,
)

ARABI_2022 = HistoricEvent(
    name="Arabi EF3 Tornado",
    event_type="tornado",
    date=datetime(2022, 3, 23, tzinfo=timezone.utc),
    closest_approach=datetime(2022, 3, 23, 0, 30, tzinfo=timezone.utc),
    latitude=29.9544,
    longitude=-90.0053,
    intensity="EF3 (strongest on record for NOLA metro)",
    description="11.5-mile path through Lower 9th Ward and Arabi. 160 mph, 1 death. KLIX radar ~25 km.",
    cwop_region="New Orleans metro (moderate coverage)",
    radar_station="KLIX",
    freezing_level_m=3000,
    approach_duration_min=60,
    departure_duration_min=15,
)

# ============================================================================
# ALL EVENTS (for iteration)
# ============================================================================

ALL_TORNADO_EVENTS = [
    MOORE_2013,
    EL_RENO_2013,
    JOPLIN_2011,
    TUSCALOOSA_2011,
    PILGER_2014,
    NEWNAN_2021,
    ARABI_2022,
]

ALL_SEVERE_THUNDERSTORM_EVENTS = [
    OKLAHOMA_DERECHO_2012,
    GIANT_HAIL_2021,
]

ALL_EVENTS = ALL_TORNADO_EVENTS + ALL_SEVERE_THUNDERSTORM_EVENTS


def get_event_by_name(name: str) -> Optional[HistoricEvent]:
    """Get event by name."""
    for event in ALL_EVENTS:
        if event.name.lower() == name.lower():
            return event
    return None
