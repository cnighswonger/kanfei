"""APRS (Automatic Packet Reporting System) weather format stub.

Defines the APRSInterface protocol and a concrete implementation that
can format Davis weather data into APRS weather report packets.

APRS weather format (from the APRS spec):
    @DDHHMMz lat/lon_wind-dir/wind-speed gust temp rain-hr rain-24 rain-midnight humidity baro

Example APRS weather string:
    @151753z4903.50N/07201.75W_270/010g015t072r000p000P000h50b10132

Reference: http://www.aprs.org/doc/APRS101.PDF Chapter 12
"""

from datetime import datetime, timezone
from typing import Optional, Protocol, runtime_checkable


@runtime_checkable
class APRSInterface(Protocol):
    """Protocol class defining the APRS weather packet interface.

    Implementations must provide format_packet() to produce a valid
    APRS weather format string, and send() to transmit the packet.
    """

    def format_packet(self) -> str:
        """Format current weather data as an APRS weather packet string.

        Returns:
            APRS-formatted weather report string.
        """
        ...

    def send(self) -> None:
        """Transmit the formatted APRS packet.

        Raises:
            NotImplementedError: This method is not yet implemented.
        """
        ...


class APRSWeatherPacket:
    """Formats Davis weather station data into APRS weather report packets.

    All values are stored in Davis native units and converted to APRS
    format (which uses its own unit conventions) during formatting.

    APRS weather field conventions:
        - Wind direction: degrees (3 digits)
        - Wind speed: mph (3 digits)
        - Wind gust: mph (3 digits)
        - Temperature: Fahrenheit (3 digits, negative uses '-')
        - Rain last hour: hundredths of inch (3 digits)
        - Rain last 24h: hundredths of inch (3 digits)
        - Rain since midnight: hundredths of inch (3 digits)
        - Humidity: percent (2 digits, 00 = 100%)
        - Barometric pressure: tenths of hPa (5 digits)
    """

    def __init__(
        self,
        callsign: str,
        latitude: float,
        longitude: float,
        wind_dir_deg: Optional[int] = None,
        wind_speed_tenths_ms: int = 0,
        wind_gust_tenths_ms: int = 0,
        temp_tenths_c: int = 222,
        rain_hour_tenths_mm: int = 0,
        rain_24h_tenths_mm: int = 0,
        rain_midnight_tenths_mm: int = 0,
        humidity_pct: int = 0,
        pressure_tenths_hpa: int = 10132,
        obs_time: Optional[datetime] = None,
    ) -> None:
        """Initialize an APRS weather packet.

        All values in SI units.

        Args:
            callsign: Amateur radio callsign (e.g., "N0CALL").
            latitude: Station latitude in decimal degrees.
            longitude: Station longitude in decimal degrees.
            wind_dir_deg: Wind direction in degrees (0-359), or None if calm.
            wind_speed_tenths_ms: Sustained wind speed in tenths of m/s.
            wind_gust_tenths_ms: Wind gust speed in tenths of m/s.
            temp_tenths_c: Temperature in tenths of °C.
            rain_hour_tenths_mm: Rain in last hour (tenths of mm).
            rain_24h_tenths_mm: Rain in last 24 hours (tenths of mm).
            rain_midnight_tenths_mm: Rain since midnight (tenths of mm).
            humidity_pct: Relative humidity 0-100%.
            pressure_tenths_hpa: Sea-level barometric pressure in tenths of hPa.
            obs_time: Observation UTC time (defaults to now).
        """
        self.callsign = callsign
        self.latitude = latitude
        self.longitude = longitude
        self.wind_dir_deg = wind_dir_deg
        self.wind_speed_tenths_ms = wind_speed_tenths_ms
        self.wind_gust_tenths_ms = wind_gust_tenths_ms
        self.temp_tenths_c = temp_tenths_c
        self.rain_hour_tenths_mm = rain_hour_tenths_mm
        self.rain_24h_tenths_mm = rain_24h_tenths_mm
        self.rain_midnight_tenths_mm = rain_midnight_tenths_mm
        self.humidity_pct = humidity_pct
        self.pressure_tenths_hpa = pressure_tenths_hpa
        self.obs_time = obs_time or datetime.now(timezone.utc)

    def _format_latitude(self) -> str:
        """Format latitude as APRS DDMM.MMN/S.

        Returns:
            APRS latitude string, e.g., '4903.50N'.
        """
        hemisphere = "N" if self.latitude >= 0 else "S"
        abs_lat = abs(self.latitude)
        degrees = int(abs_lat)
        minutes = (abs_lat - degrees) * 60.0
        return f"{degrees:02d}{minutes:05.2f}{hemisphere}"

    def _format_longitude(self) -> str:
        """Format longitude as APRS DDDMM.MME/W.

        Returns:
            APRS longitude string, e.g., '07201.75W'.
        """
        hemisphere = "E" if self.longitude >= 0 else "W"
        abs_lon = abs(self.longitude)
        degrees = int(abs_lon)
        minutes = (abs_lon - degrees) * 60.0
        return f"{degrees:03d}{minutes:05.2f}{hemisphere}"

    def _pressure_to_aprs(self, tenths_hpa: int) -> int:
        """Convert tenths of hPa to APRS barometric pressure (tenths of hPa).

        APRS barometric pressure is already in tenths of millibars (hPa),
        which is the same as our SI storage unit. Pass through.

        Args:
            tenths_hpa: Pressure in tenths of hPa.

        Returns:
            Pressure in tenths of hPa (unchanged).
        """
        return tenths_hpa

    def format_packet(self) -> str:
        """Format current weather data as an APRS weather packet string.

        Produces a complete APRS weather report in the standard format:
            @DDHHMMzLAT/LON_DDD/SSSgGGGtTTTrRRRpPPPPPPhHHbBBBBB

        Returns:
            APRS-formatted weather report string.
        """
        # Timestamp: DDHHMMz
        time_str = self.obs_time.strftime("%d%H%Mz")

        # Position
        lat_str = self._format_latitude()
        lon_str = self._format_longitude()

        # Wind direction (3 digits, 000 if calm)
        wind_dir = self.wind_dir_deg if self.wind_dir_deg is not None else 0
        dir_str = f"{wind_dir:03d}"

        # Wind speed (3 digits, mph) — convert from tenths m/s
        wind_mph = round(self.wind_speed_tenths_ms / 10.0 * 2.23694)
        spd_str = f"{wind_mph:03d}"

        # Wind gust (3 digits, mph)
        gust_mph = round(self.wind_gust_tenths_ms / 10.0 * 2.23694)
        gust_str = f"{gust_mph:03d}"

        # Temperature (3 digits, whole degrees F) — convert from tenths °C
        temp_f = round(self.temp_tenths_c / 10.0 * 9 / 5 + 32)
        temp_str = f"{temp_f:03d}"

        # Rain (3 digits each, hundredths of inch) — convert from tenths mm
        rain_hr_in = round(self.rain_hour_tenths_mm / 10.0 / 25.4 * 100)
        rain_24_in = round(self.rain_24h_tenths_mm / 10.0 / 25.4 * 100)
        rain_mid_in = round(self.rain_midnight_tenths_mm / 10.0 / 25.4 * 100)
        rain_hr = f"{rain_hr_in:03d}"
        rain_24 = f"{rain_24_in:03d}"
        rain_mid = f"{rain_mid_in:03d}"

        # Humidity (2 digits, 00 = 100%)
        hum = self.humidity_pct % 100  # 100 becomes 00
        hum_str = f"{hum:02d}"

        # Barometric pressure (5 digits, tenths of hPa) — already SI
        baro_str = f"{self.pressure_tenths_hpa:05d}"

        # Assemble the packet
        packet = (
            f"@{time_str}"
            f"{lat_str}/{lon_str}"
            f"_{dir_str}/{spd_str}"
            f"g{gust_str}"
            f"t{temp_str}"
            f"r{rain_hr}"
            f"p{rain_24}"
            f"P{rain_mid}"
            f"h{hum_str}"
            f"b{baro_str}"
        )

        return packet

    def send(self) -> None:
        """Transmit the APRS packet.

        Raises:
            NotImplementedError: APRS transmission is not yet implemented.
                Future implementations may use APRS-IS (internet) or
                a TNC (radio) backend.
        """
        raise NotImplementedError(
            "APRS packet transmission is not yet implemented. "
            "Future versions will support APRS-IS and TNC backends."
        )
