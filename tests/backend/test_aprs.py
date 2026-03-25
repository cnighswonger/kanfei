"""Tests for APRS weather packet formatting (SI inputs)."""

from datetime import datetime, timezone

from app.output.aprs import APRSWeatherPacket


class TestAPRSLatitude:

    def test_north_hemisphere(self):
        pkt = APRSWeatherPacket("N0CALL", 49.0583, -72.0292)
        assert pkt._format_latitude() == "4903.50N"

    def test_south_hemisphere(self):
        pkt = APRSWeatherPacket("N0CALL", -33.8688, 151.2093)
        assert pkt._format_latitude() == "3352.13S"

    def test_equator(self):
        pkt = APRSWeatherPacket("N0CALL", 0.0, 0.0)
        assert pkt._format_latitude() == "0000.00N"


class TestAPRSLongitude:

    def test_west_hemisphere(self):
        pkt = APRSWeatherPacket("N0CALL", 49.0583, -72.0292)
        assert pkt._format_longitude() == "07201.75W"

    def test_east_hemisphere(self):
        pkt = APRSWeatherPacket("N0CALL", 0.0, 151.2093)
        assert pkt._format_longitude() == "15112.56E"

    def test_prime_meridian(self):
        pkt = APRSWeatherPacket("N0CALL", 0.0, 0.0)
        assert pkt._format_longitude() == "00000.00E"


class TestAPRSPressureConversion:

    def test_standard_pressure(self):
        pkt = APRSWeatherPacket("N0CALL", 0.0, 0.0)
        # tenths hPa pass through directly to APRS (already tenths hPa)
        result = pkt._pressure_to_aprs(10132)
        assert result == 10132

    def test_low_pressure(self):
        pkt = APRSWeatherPacket("N0CALL", 0.0, 0.0)
        result = pkt._pressure_to_aprs(9650)
        assert result == 9650


class TestAPRSFormatPacket:

    def test_packet_structure(self):
        obs = datetime(2026, 3, 15, 17, 53, 0, tzinfo=timezone.utc)
        pkt = APRSWeatherPacket(
            callsign="N0CALL",
            latitude=49.0583,
            longitude=-72.0292,
            wind_dir_deg=270,
            wind_speed_tenths_ms=45,     # 4.5 m/s ≈ 10 mph
            wind_gust_tenths_ms=67,      # 6.7 m/s ≈ 15 mph
            temp_tenths_c=222,           # 22.2°C = 72°F
            humidity_pct=50,
            pressure_tenths_hpa=10132,   # 1013.2 hPa
            obs_time=obs,
        )
        result = pkt.format_packet()
        assert result.startswith("@151753z")
        assert "4903.50N" in result
        assert "07201.75W" in result
        assert "_270/010" in result
        assert "g015" in result
        assert "t072" in result
        assert "h50" in result
        assert "b10132" in result

    def test_humidity_100_becomes_00(self):
        obs = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        pkt = APRSWeatherPacket(
            callsign="N0CALL", latitude=0.0, longitude=0.0,
            humidity_pct=100, obs_time=obs,
        )
        assert "h00" in pkt.format_packet()

    def test_calm_wind(self):
        obs = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        pkt = APRSWeatherPacket(
            callsign="N0CALL", latitude=0.0, longitude=0.0,
            wind_dir_deg=None, wind_speed_tenths_ms=0, obs_time=obs,
        )
        assert "_000/000" in pkt.format_packet()

    def test_negative_temperature(self):
        obs = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        pkt = APRSWeatherPacket(
            callsign="N0CALL", latitude=0.0, longitude=0.0,
            temp_tenths_c=-233, obs_time=obs,  # -23.3°C ≈ -10°F
        )
        result = pkt.format_packet()
        assert "t-10" in result

    def test_rain_fields(self):
        obs = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        pkt = APRSWeatherPacket(
            callsign="N0CALL", latitude=0.0, longitude=0.0,
            rain_hour_tenths_mm=13,       # 1.3 mm ≈ 0.05 in → 5 hundredths
            rain_24h_tenths_mm=64,        # 6.4 mm ≈ 0.25 in → 25 hundredths
            rain_midnight_tenths_mm=30,   # 3.0 mm ≈ 0.12 in → 12 hundredths
            obs_time=obs,
        )
        result = pkt.format_packet()
        assert "r005" in result
        assert "p025" in result
        assert "P012" in result

    def test_send_raises(self):
        pkt = APRSWeatherPacket("N0CALL", 0.0, 0.0)
        try:
            pkt.send()
            assert False, "Should have raised NotImplementedError"
        except NotImplementedError:
            pass
