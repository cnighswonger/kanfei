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
        wind_speed_mph: int = 0,
        wind_gust_mph: int = 0,
        temp_tenths_f: int = 720,
        rain_hour_hundredths_in: int = 0,
        rain_24h_hundredths_in: int = 0,
        rain_midnight_hundredths_in: int = 0,
        humidity_pct: int = 0,
        barometer_thousandths_inhg: int = 29920,
        obs_time: Optional[datetime] = None,
    ) -> None:
        """Initialize an APRS weather packet.

        Args:
            callsign: Amateur radio callsign (e.g., "N0CALL").
            latitude: Station latitude in decimal degrees.
            longitude: Station longitude in decimal degrees.
            wind_dir_deg: Wind direction in degrees (0-359), or None if calm.
            wind_speed_mph: Sustained wind speed in mph.
            wind_gust_mph: Wind gust speed in mph.
            temp_tenths_f: Temperature in tenths of degrees Fahrenheit.
            rain_hour_hundredths_in: Rain in last hour (hundredths of inch).
            rain_24h_hundredths_in: Rain in last 24 hours (hundredths of inch).
            rain_midnight_hundredths_in: Rain since midnight (hundredths of inch).
            humidity_pct: Relative humidity 0-100%.
            barometer_thousandths_inhg: Sea-level barometric pressure in
                thousandths of inHg.
            obs_time: Observation UTC time (defaults to now).
        """
        self.callsign = callsign
        self.latitude = latitude
        self.longitude = longitude
        self.wind_dir_deg = wind_dir_deg
        self.wind_speed_mph = wind_speed_mph
        self.wind_gust_mph = wind_gust_mph
        self.temp_tenths_f = temp_tenths_f
        self.rain_hour_hundredths_in = rain_hour_hundredths_in
        self.rain_24h_hundredths_in = rain_24h_hundredths_in
        self.rain_midnight_hundredths_in = rain_midnight_hundredths_in
        self.humidity_pct = humidity_pct
        self.barometer_thousandths_inhg = barometer_thousandths_inhg
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

    def _inhg_to_tenths_hpa(self, thousandths_inhg: int) -> int:
        """Convert thousandths of inHg to tenths of hPa.

        APRS barometric pressure is in tenths of millibars (hPa).
        1 inHg = 33.8639 hPa

        Args:
            thousandths_inhg: Pressure in thousandths of inHg.

        Returns:
            Pressure in tenths of hPa.
        """
        inhg = thousandths_inhg / 1000.0
        hpa = inhg * 33.8639
        return round(hpa * 10)

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

        # Wind speed (3 digits, mph)
        spd_str = f"{self.wind_speed_mph:03d}"

        # Wind gust (3 digits, mph)
        gust_str = f"{self.wind_gust_mph:03d}"

        # Temperature (3 digits, whole degrees F)
        temp_f = round(self.temp_tenths_f / 10.0)
        if temp_f < 0:
            temp_str = f"{temp_f:03d}"  # Includes minus sign
        else:
            temp_str = f"{temp_f:03d}"

        # Rain (3 digits each, hundredths of inch)
        rain_hr = f"{self.rain_hour_hundredths_in:03d}"
        rain_24 = f"{self.rain_24h_hundredths_in:03d}"
        rain_mid = f"{self.rain_midnight_hundredths_in:03d}"

        # Humidity (2 digits, 00 = 100%)
        hum = self.humidity_pct % 100  # 100 becomes 00
        hum_str = f"{hum:02d}"

        # Barometric pressure (5 digits, tenths of hPa)
        baro_tenths_hpa = self._inhg_to_tenths_hpa(self.barometer_thousandths_inhg)
        baro_str = f"{baro_tenths_hpa:05d}"

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
