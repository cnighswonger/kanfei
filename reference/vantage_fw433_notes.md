# Vantage Vue Console fw 4.33 — findings log

Running notes on an in-hand Vantage Vue Console reporting firmware
version `4.33`, dated `Apr 16 2018`, manufactured `2018-07-17`
(serial `MR180717019`).

The Davis KB firmware page
(https://www.manula.com/manuals/pws/davis-kb/1/en/topic/updating-console-firmware)
lists documented Vue Console versions as `v2.12, v2.14, v3.00, v4.18,
v4.30`, so 4.33 is a minor step above the last publicly-listed
version and IS a legitimate Davis firmware, contrary to what a
web search or Gemini will tell you (both turn up nothing for Vue
> 3.x).  The reason the internet is silent on 4.x is (per hearsay
Chris relayed 2026-08-12, unverified): **Davis has not released any
public update mechanism since v3.00**.  Post-MB Vue consoles were
flashed with 4.x at production time and there is no user-facing
update path.  If that's true it explains the silence and it makes
the bench Vue effectively frozen at 4.33 — no accidental update is
possible.

The on-disk Davis Serial Communication Reference
(`vantage_serial_ref_v261.txt`) corresponds to the pre-4.x-firmware
protocol.  Where 4.33's wire behaviour differs, we track it here.

Purpose of this doc: track differences between what fw 4.33 does on
the wire vs. what the reference (or the older-firmware behaviour we
have production data for) says it should.  Sibling to
`vantage_dash_values.md` which tracks a similar catalogue for
sensor-value quirks.

## Unit provenance

| | Value |
|---|---|
| Product line | Vantage Vue Console (Model 6250) |
| Serial number | `MR180717019` |
| Manufacture date | 2018-07-17 (decoded from serial) |
| Firmware version (`NVER`) | `4.33` |
| Firmware date (`VER`) | `Apr 16 2018` |
| Station type code (returned by driver) | `17` (matches Vue) |
| Capabilities advertised | archive_period_rw, archive_sync, barometer_cal, calibration_rw, clock_sync, hilows, location_rw, rain_reset, rain_season_rw |

Comparison point: our production Vantage Vue is a Model 6250 too,
serial `D100908A018` (Sep 8 2010), fw `2.12` (Oct 12 2009).

## Verified departures from documented / expected behaviour

### 1. `NEWSETUP` applies SETUP_BITS without a power cycle

Documented (older firmware): after writing `EEBWR 0x2B`, the console
LCD driver typically does NOT pick up the change until a hardware
power cycle.  `NEWSETUP` re-inits the microcontroller state but
older Vue displays commonly need battery-pull-and-repower to fully
reflect display-format bits.

Observed (fw 4.33, this unit): after `EEBWR 0x2B` + `NEWSETUP`, the
front-panel date format changed from `12.08` (Day/Month) to `8/12`
(Month/Day) immediately, no power cycle required.

Load-bearing?  This changes the ergonomics of on-wire display
setting: on this firmware we can flip display bits and see the
result without touching hardware.

## Verified matches to documented behaviour

- `NVER` / `VER` / station-type-code parsing all work as the driver
  expects — the "4.33" version string is just a bigger number than
  we'd seen before, not a different response shape.
- `EEBRD` / `EEBWR` at 0x2B behave normally: single-byte read/write
  with the standard ACK protocol.
- `SETUP_BITS` bit layout matches the reference (v2.6.1) exactly on
  the bits we've actually flipped:
  - Bit 0: AM/PM Time Mode (12h vs 24h) — verified
  - Bit 2: Month/Day format — verified
  - Bit 6: Latitude hemisphere (North/South) — verified (clearing
    left the display consistent with N-hemisphere position after
    location write; setting it explicitly north was decorative but
    correct)

## Not yet verified — open bits

- Bit 1: AM/PM indicator — not tested; console updates this
  automatically on time progression.
- Bit 3: Wind cup size — documented as "VP and VP2 only" (§XIV.4).
  Bench was set to 1 (large) from the factory / previous owner.
  Cleared to 0 as part of the sync, no verified effect on wire.
- Bit 4–5: Rain collector size — bench was at 00 (0.01 in),
  matches Vue standard.  Not deliberately flipped.
- Bit 7: Longitude hemisphere (East/West) — bench correctly at 0
  (West).  Not deliberately flipped.

## Open questions

- Where does fw 4.33 store other display preferences that are
  visible on the front-panel setup wizard (time zone, DST mode,
  wind display units, etc.) — are they in EEPROM addresses the
  reference documents, or somewhere new?
- Does the wire behaviour of `BAR=` differ from older firmware?
  #257 documented specific quirks (NAK still applies elevation, 504
  yet applied, etc.) on fw 3.0 and older; fw 4.33 may or may not
  reproduce.
- Does `RXCHECK` field layout match?  Documented as
  packets_received / missed / resync / max_consecutive_received /
  crc_errors on fw 2.12.  On fw 4.33 first read we got the same
  five fields with sane values (`19683 118 0 1046 40`) — matches.
- Is there a way to query the firmware for whether it accepts an
  extended command set (LOOP2 fields not in the older reference,
  additional EEPROM addresses, etc.)?

## How to add findings

When you discover a wire-vs-doc conflict, append a subsection under
"Verified departures" (or "Verified matches" if the doc holds).
Include:

1. What the doc says (with reference/section pointer)
2. What the wire does (with the command sequence and the observed
   response)
3. Consequences — e.g. "the driver's `_h_set_bar` handler treats
   NAK as no-op, which is wrong on this firmware because…"

Reference incidents / issues where relevant (e.g. #257, #297).

## Hardware-revision safety note

The KB is explicit about a destructive combination:

> Vue consoles prior to revision **MB** (i.e. MA and older) should
> not be updated to firmware later than v3.00.  Any attempt to
> update older Vue consoles to v4.18 or later is likely to stop
> Weatherlink loggers from working.

Applied here:

- **Production Vue** (`D100908A018`, Sept 2010, fw 2.12) — almost
  certainly a pre-MB revision.  Must never be updated to any
  firmware ≥ 4.18.  Sticking with 2.12 keeps its datalogger safe.
- **Bench Vue** (`MR180717019`, July 2018, fw 4.33) — post-MB
  hardware that shipped from Davis with 4.x factory-flashed
  firmware.  Nominally safe to update within the 4.x line, but per
  the hearsay above there is no user-facing update path, so the
  question is moot.

## Update tool (context)

Per the same KB page: "Console firmware updates can only be made
from Windows PCs."  No firmware operations are possible from
vsits-02 or any Mac/Linux dev machine regardless.  The 6313
Weatherlink Console (a different product from the 6250 Vue
Console) updates itself over the Internet — noting because Google
searches for "Vantage Console firmware" tend to conflate the two.

## Related

- `vantage_dash_values.md` — catalogue of sensor-value wire vs
  manual disagreements
- `vantage_serial_ref_v261.txt` — the on-disk Davis reference the
  driver is written against
- Davis KB firmware page —
  https://www.manula.com/manuals/pws/davis-kb/1/en/topic/updating-console-firmware
- Issue #297 — bench Vue wire-analysis tracker
