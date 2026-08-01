# Davis Vantage "dashed" / no-sensor values

What each field reads when no sensor is present or the console has no data.
Compiled from the Vantage Serial Communication Reference v2.6.1 and from
measurements on a Vantage Vue (fw 2.12).

## Why this exists

Five separate bugs on this project came from an unfiltered sentinel, each
found downstream by a value looking wrong rather than by design:

| symptom | field | sentinel |
|---|---|---|
| six phantom extra-temp sensors at -90 °F | extra temps | `0xFF` |
| sunrise displayed as `00:00` | sunrise | `0` (+ wrong offset) |
| 255 mph gust published to APRS for hours | LOOP wind speed | `255` |
| unpopulated hi/low slots reading as data | HILOWS block | mixed |
| dashed humidity as `255%` | humidity | `0xFF` |

## The rule that actually holds

**A sentinel is only safely detectable when it falls outside the field's
physical range.**

Where the documented dash value sits *inside* the plausible range it
cannot be distinguished from real data, and filtering it destroys valid
readings. This is not a gap to be closed — it is a property of the
encoding.

## Sentinels that ARE safely detectable

Outside the physical range, so filtering is unambiguous.

| Field | Width | Dash | Notes |
|---|---|---|---|
| Outside/inside temp | s16 | `32767` (`0x7FFF`) | tenths °F |
| Low temp (archive) | s16 | `32767` | |
| **High** temp (archive) | s16 | **`-32768`** | different from the others |
| Humidity (all) | u8 | `255` | also reject `>100` |
| UV index | u8 | `255` | |
| Solar radiation | u16 | `32767` | |
| Wind direction | u16 | `32767`, or `>360` | |
| Wind dir code (archive) | u8 | `255` | see manual error below |
| Rain rate | u16 | `65535` (`0xFFFF`) | |
| Extra/soil/leaf temps | u8 | `255` | offset-encoded, °F+90 |
| Soil moisture | u8 | `255` | |
| Leaf wetness | u8 | `255` | also reject `>15` |
| **LOOP wind speed** | u8 | `255` | *was unfiltered — see below* |
| Sunrise / sunset | u16 | `65535`, and `0` | 0 is never a real sun time |

## Sentinels that are NOT safely detectable

The documented dash value is a legitimate reading. **Do not filter these.**

| Field | Dash | Why it cannot be honoured |
|---|---|---|
| High Wind Speed (archive) | `0` | 0 mph = no gust in the interval. Real. |
| Rainfall | `0` | 0 = no rain. Real, and the common case. |
| High Rain Rate | `0` | same |
| Barometer | `0` | technically detectable — no station reads 0 inHg — and we do filter it. Listed here because the manual gives the same `0` that is un-filterable elsewhere. |
| ET | `0` | 0 = no evapotranspiration that hour. Real. |
| Reed switch counts | `0` | 0 = no closures. Real. |
| Number of wind samples | `0` | 0 = none received. Real. |

## Errors in the manual's own dash column

- **Direction of Hi Wind Speed** (archive offset 26) is listed as dash
  `32767` in a **1-byte** field. That value cannot fit. The Explanation
  column two lines away says "255 = Dashed", which is correct.
- **Prevailing Wind Direction** (offset 27) has the same contradiction.
- The **LOOP** tables have no Dash Value column at all — only the archive
  tables do. So the LOOP sentinels above are inferred from the archive
  equivalents and confirmed on the wire, which is precisely why LOOP is
  where all the parsing bugs were.

## Measured, not documented

- **LOOP byte 86** (transmitter battery status): the manual names the
  field but documents no bit layout. Bit N = transmitter N+1, inferred and
  corroborated on a Vue whose console displayed an ISS low-battery warning
  while this byte read `0x01`.
- **A stuck sentinel does not look like noise.** It looks like a sustained
  reading and it is self-consistent across polls. The 255 mph gust held
  one value for 27 minutes across 107 rows. The giveaway is the company it
  keeps: during a dropout, every *other* outdoor field is None. Testing
  that whole shape catches more than testing fields individually.
- **An extreme is stickier than a reading.** A sentinel that reaches a
  daily maximum outlives the outage and keeps being republished until
  midnight rollover — including to APRS/CWOP and Weather Underground,
  which both source their gust from `daily_extremes.wind_speed_hi`.

## Coverage

`archive.py` guards nearly every field and has for some time.
`loop_packet.py` was the patchy one — all five bugs above came from it.
Worth auditing any *new* LOOP field against this table before use.
