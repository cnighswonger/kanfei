"""Tests for APRS weather packet formatting."""

from datetime import datetime, timezone

from app.output.aprs import APRSWeatherPacket


class TestAPRSLatitude:

    def test_north_hemisphere(self):
        pkt = APRSWeatherPacket("N0CALL", 49.0583, -72.0292)
        assert pkt._format_latitude() == "4903.50N"

    def test_south_hemisphere(self):
        pkt = APRSWeatherPacket("N0CALL", -33.8688, 151.2093)
        # 33.8688° S → 33°52.13'S
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
        # 151.2093° E → 151°12.56'E
        assert pkt._format_longitude() == "15112.56E"

    def test_prime_meridian(self):
        pkt = APRSWeatherPacket("N0CALL", 0.0, 0.0)
        assert pkt._format_longitude() == "00000.00E"


class TestAPRSPressureConversion:

    def test_standard_pressure(self):
        pkt = APRSWeatherPacket("N0CALL", 0.0, 0.0)
        # 29.92 inHg = 1013.25 hPa → 10132 tenths
        result = pkt._inhg_to_tenths_hpa(29920)
        assert 10130 <= result <= 10135

    def test_low_pressure(self):
        pkt = APRSWeatherPacket("N0CALL", 0.0, 0.0)
        # 28.50 inHg ≈ 965 hPa → ~9650 tenths
        result = pkt._inhg_to_tenths_hpa(28500)
        assert 9640 <= result <= 9660


class TestAPRSFormatPacket:

    def test_packet_structure(self):
        obs = datetime(2026, 3, 15, 17, 53, 0, tzinfo=timezone.utc)
        pkt = APRSWeatherPacket(
            callsign="N0CALL",
            latitude=49.0583,
            longitude=-72.0292,
            wind_dir_deg=270,
            wind_speed_mph=10,
            wind_gust_mph=15,
            temp_tenths_f=720,
            humidity_pct=50,
            barometer_thousandths_inhg=29920,
            obs_time=obs,
        )
        assert pkt.format_packet() == "@151753z4903.50N/07201.75W_270/010g015t072r000p000P000h50b10132"

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
            wind_dir_deg=None, wind_speed_mph=0, obs_time=obs,
        )
        assert "_000/000" in pkt.format_packet()

    def test_negative_temperature(self):
        obs = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        pkt = APRSWeatherPacket(
            callsign="N0CALL", latitude=0.0, longitude=0.0,
            temp_tenths_f=-100, obs_time=obs,  # -10°F
        )
        result = pkt.format_packet()
        assert "t-10" in result

    def test_rain_fields(self):
        obs = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        pkt = APRSWeatherPacket(
            callsign="N0CALL", latitude=0.0, longitude=0.0,
            rain_hour_hundredths_in=5,
            rain_24h_hundredths_in=25,
            rain_midnight_hundredths_in=12,
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
