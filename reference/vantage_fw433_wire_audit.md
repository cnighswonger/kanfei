# Vantage Vue fw 4.33 — full wire audit report

Full audit of the bench Vue Console (serial `MR180717019`, fw 4.33
dated `Apr 16 2018`) against the Davis Serial Communication Reference
v2.6.1 (`vantage_serial_ref_v261.txt`) and the assumptions baked into
`VantageDriver` (written against fw 2.12/3.0).

Read-only audit; no state changes.  Captured on 2026-08-12 from
vsits-02's ttyUSB4.  Companion to `vantage_fw433_notes.md`, which
holds the running notes on individual findings as they accumulate;
this report is the snapshot of a single audit pass.

## Executive summary

- **28 documented behaviors verified** — bench Vue matches
  documented / expected behavior for the core protocol.
- **3 departures identified** — one benign (unsupported command;
  driver doesn't use it), one anomaly worth flagging
  (`TEMP_OUT_COMP` invariant broken), one cosmetic (ACK byte
  semantics on `RECEIVERS`).
- **2 undocumented commands discovered** — `IDENT` (returns product
  number), `HELP` (returns horizontal-rule; likely interactive).
- **EEPROM address map matches documentation** for every field
  tested.  No evidence of a wholesale remap.

Bottom line: fw 4.33 is protocol-compatible with fw ≤3.0 for
everything the driver actually uses.  The one substantive
departure (`TEMP_OUT_COMP`) needs a write-test follow-up before
we can say whether it affects calibration writes.

## Verified UNCHANGED from documented behavior

| Area | Command | Observation | Match |
|---|---|---|---|
| Identity | `VER` | `\n\rOK\n\rApr 16 2018\n\r` | ✓ format |
| Identity | `NVER` | `\n\rOK\n\r4.33\n\r` | ✓ format |
| Identity | station_type_code | `17` (0x11) | ✓ Vue |
| Data | `LOOP 1` | 99 bytes, `LOO` prefix, packet_type=0x00 at byte 4, `\n\r` + CRC trailer | ✓ layout |
| Data | `LPS 2 1` (LOOP2) | 99 bytes, `LOO` prefix, packet_type=**0x01** at byte 4 | ✓ layout — LOOP2 IS supported on fw 4.33 |
| Data | `LPS 3 1` (both) | LOOP frame first (byte 4 = 0x00) | ✓ ordering |
| Time | `GETTIME` | 8 bytes = [sec, min, hour, day, month, year-1900, crc, crc] = `26 27 10 0c 08 7e af bf` = 2026-08-12 16:39:38 | ✓ order + range |
| Signal | `RXCHECK` | `\n\rOK\n\r<pkts> <missed> <resync> <max_run> <crc_err>\n\r` = `1400 9 0 570 4` | ✓ format + 5 fields |
| Signal | `RXCHECK` field order | packets_received / missed / resync / max_consecutive_received / crc_errors (fields 4 is a run of SUCCESSES not misses) | ✓ [[feedback_rxcheck_field_semantics]] holds on 4.33 |
| Data | `HILOWS` | 438 bytes (436 data + 2 CRC), starts with sensible sensor bytes | ✓ length + CRC |
| Data | `GETEE` | 4098 bytes (4096 EEPROM + 2 CRC) | ✓ length + CRC |
| Cal | `BARDATA` | ASCII fields `BAR nnnnn\n\rELEVATION nnn\n\rDEW POINT nn\n\rVIRTUAL TEMP nn\n\rC nn\n\rR nnnn\n\r` | ✓ exactly |
| Test | `TEST` | Echoes back: `\n\rTEST\n\r` | ✓ |
| EEPROM | `LATITUDE` (0x0B, 2 bytes) | 354 decimal → 35.4°N (matches bench sync) | ✓ address + encoding |
| EEPROM | `LONGITUDE` (0x0D, 2 bytes) | -786 decimal → -78.6°W | ✓ |
| EEPROM | `ELEVATION` (0x0F, 2 bytes) | 265 ft | ✓ |
| EEPROM | `TIME_ZONE` (0x11) | 10 (US Eastern preset per Davis table) | ✓ |
| EEPROM | `GMT_OFFSET` (0x14, 2 bytes) | -500 (hundredths hours) → -5.00 h | ✓ EDT baseline (DST logic on top) |
| EEPROM | `USE_TX` (0x17) | 0x01 = single transmitter enabled | ✓ Vue-normal |
| EEPROM | `STATION_LIST` (0x19, 16 bytes) | ID 1: type 0 (ISS), IDs 2-8 unused | ✓ Vue-normal |
| EEPROM | `UNIT_BITS` (0x29) | 0x00 = all US defaults | ✓ |
| EEPROM | `SETUP_BITS` (0x2B) | 0x40 = 12h/AM/Month-Day/small cup/0.01 in/N/W (after bench sync) | ✓ |
| EEPROM | `RAIN_SEASON_START` (0x2C) | 1 (January, matching prod) | ✓ |
| EEPROM | `ARCHIVE_PERIOD` (0x2D) | 1 min (matching prod) | ✓ |
| EEPROM | 1's-complement invariant | `UNIT_BITS`/`UNIT_BITS_COMP` at 0x29/0x2A: 0x00/0xFF ✓; `TEMP_IN_CAL`/`TEMP_IN_COMP` at 0x32/0x33: 0x00/0xFF ✓ | ✓ (see departures for the one that fails) |
| Protocol | CRC-16 | Verified over `HILOWS` and `GETEE` blocks — CRC bytes decode against the documented Davis polynomial | ✓ |
| Protocol | ACK byte | 0x06 returned before binary data blocks (`LOOP`, `LPS`, `HILOWS`, `GETEE`, `GETTIME`) | ✓ |
| Protocol | Text-response format | `\n\rOK\n\r<data>\n\r` for ASCII commands (`VER`, `NVER`, `RXCHECK`) | ✓ |

## Departures from documentation

### D1. `GETPER` silently unsupported (benign)

**Documented behavior**: `GETPER` returns the current archive-period
value as an ASCII line, same format as `RXCHECK`.

**Observed on fw 4.33**: send `GETPER\n`, wait 5 seconds, response is
2 bytes (`\n\r`) — no `OK`, no value.  Command is silently unsupported.

**Impact**: **None on the driver.**  `VantageDriver.async_read_archive_period()`
reads EEPROM 0x2D directly rather than using `GETPER`, so the driver
never encounters this.  Behavior noted for anyone porting to
third-party code that might use `GETPER`.

### D2. `TEMP_OUT_COMP` invariant broken

**Documented behavior**: `TEMP_OUT_COMP` at EEPROM 0x35 is the 1's
complement of `TEMP_OUT_CAL` at 0x34.  Every write to `TEMP_OUT_CAL`
should update `TEMP_OUT_COMP` to `0xFF ^ new_cal_value`.

**Observed on fw 4.33**: `TEMP_OUT_CAL = 0x00`, `TEMP_OUT_COMP = 0x00`.
The invariant does NOT hold.  Contrast:

- `TEMP_IN_CAL` (0x32) = 0x00, `TEMP_IN_COMP` (0x33) = 0xFF — invariant HOLDS
- `UNIT_BITS` (0x29) = 0x00, `UNIT_BITS_COMP` (0x2A) = 0xFF — invariant HOLDS
- `TEMP_OUT_CAL` (0x34) = 0x00, `TEMP_OUT_COMP` (0x35) = **0x00** — invariant **BROKEN**

**Two hypotheses**:

1. **Firmware bug**: fw 4.33 fails to update `TEMP_OUT_COMP` when
   `TEMP_OUT_CAL` is at its default 0x00 (uninitialized-during-boot
   quirk), but does update it when the field is written.  Would
   affect the driver's `write_calibration()` path if it validates
   the invariant after a read-back.
2. **Address reassigned**: fw 4.33 uses 0x35 for something else.
   Would explain why the block `0x30-0x3F` (`03 01 00 ff 00 00 ff
   ff...`) looks more like a small data table than a set of cal+comp
   pairs.

**Follow-up** (not done in this audit — a write test would be
required): set `TEMP_OUT_CAL` to a small value (e.g., 0x05) via
CALED, then read 0x34 and 0x35.  If 0x35 becomes 0xFA, hypothesis 1
holds and the invariant is only broken at factory-default.  If 0x35
stays at 0x00, hypothesis 2 (or a real fw bug) is likely.

**Impact on driver**: Deferred until we run the follow-up write test.
The current driver reads calibration via `async_read_calibration()`,
which does the standard EEPROM read; it doesn't validate the
invariant, so reads are unaffected.  Writes might be — if a driver
consumer relies on the read-back-and-verify pattern to confirm a
calibration write, that verify might read a stale `TEMP_OUT_COMP`
even after a valid `TEMP_OUT_CAL` write.

### D3. `RECEIVERS` first-response-byte is 0x0A (LF), not 0x06 (ACK)

**Documented behavior**: `RECEIVERS` returns `<ACK> <bitmask>` — a
single 0x06 ACK byte followed by a single byte whose bits are set for
each transmitter ID the console has heard from.

**Observed on fw 4.33**: `<0x0A> <0x0D>` — the first byte is LF, the
second is CR.  No ACK byte, and no bitmask value.

**Explanation**: This is likely `\n\r` — the console's normal
end-of-response terminator — for a Vue that has heard no transmitter
IDs (or, on a Vue, always).  The driver's `async_receivers()`
already handles this case as "empty list" and returns `[]`, so the
observed departure is masked at the driver level.  Documenting for
future spec work — the `RECEIVERS` doc entry could use a "returns
`\n\r` when no transmitter IDs are cached" clarification.

**Impact**: **None on the driver.**

## New undocumented commands

### N1. `IDENT` returns product number

**Undocumented in Davis reference.**  Observed:

```
send:  IDENT\n
recv:  \n\r6351\n\r
```

Returns the Davis product number as a 4-character ASCII string,
prefixed and suffixed by `\n\r`.  On the bench Vue this is `6351`
(Vantage Vue Wireless with WeatherLink IP).  Would be `6250` for a
Vue Console alone; other Vantage bundles return their own SKUs.

**Potential driver use**: identify the specific product bundle at
connect time — useful for capabilities that vary by bundle (e.g.,
whether a WeatherLink IP logger is present) without inferring from
station_type_code alone.  Not adopting yet; noted for future
consideration.

### N2. `HELP` returns a horizontal-rule character block

**Undocumented in Davis reference.**  Observed:

```
send:  HELP\n
recv:  \r================================
```

32 `=` characters preceded by CR, no `OK`, no trailing `\n\r`.
Suggests an interactive HELP menu that requires user-terminal
follow-up, which the wire never receives.  **Not useful for
programmatic driver use.**  Noted for completeness.

### Undocumented probes that did NOT return meaningful data

`?\n`, `WAKEUP\n`, `WAKE\n`, `STATUS\n`, `INFO\n`, `UID\n`, `UNIT\n`,
`CAP\n` — all timed out after 5 seconds returning only a single
newline byte.  Not supported.

## EEPROM population — heatmap

Non-`0xFF` byte counts per 256-byte page in the 4096-byte EEPROM:

| Page | Range | ≠ 0xFF | ≠ 0/0xFF | Note |
|---|---|---|---|---|
| 0 | 0x000-0x0FF | 126 | 97 | Configuration block — matches documented layout |
| 1 | 0x100-0x1FF | 218 | 195 | Densely populated — likely graph data / self-recorded stats per docs |
| 2 | 0x200-0x2FF | 153 | 141 | Continued self-recorded |
| 3 | 0x300-0x3FF | 175 | 170 | Continued |
| 4 | 0x400-0x4FF | 100 | 100 | Sparser |
| 5 | 0x500-0x5FF | 177 | 165 | Populated |
| 6 | 0x600-0x6FF | 126 | 121 | |
| 7 | 0x700-0x7FF | 228 | 222 | Populated |
| 8 | 0x800-0x8FF | 254 | 248 | Nearly all populated — probably archive data start |
| 9 | 0x900-0x9FF | 148 | 79 | Populated but with lots of zeros |
| 10 | 0xA00-0xAFF | 204 | 35 | Mostly zero values (with some 0xFF gaps) |
| 11 | 0xB00-0xBFF | 131 | 24 | |
| 12 | 0xC00-0xCFF | 163 | 33 | |
| 13 | 0xD00-0xDFF | 187 | 79 | |
| 14 | 0xE00-0xEFF | 2 | 2 | Essentially empty — reserved |
| 15 | 0xF00-0xFFF | 10 | 10 | Essentially empty — reserved |

The documented EEPROM map only specifies fields in the 0x00-0x100
range.  Pages 1-13 hold data structures the Davis reference does not
enumerate at byte-level.  Consistent with the reference's statement
that archive/graph/self-recorded regions exist but should not be
directly written — no further investigation warranted absent a
specific need.

## Follow-ups this audit did not attempt

1. **Write-test for `TEMP_OUT_COMP`** — set `TEMP_OUT_CAL` via
   `CALED` on the bench, read back 0x34 and 0x35, determine which
   hypothesis (fw bug at default vs address reassigned) holds.
2. **BAR= behavior comparison** — driver code carries #257
   quirks for fw 3.0 (NAK still applies elevation, 504 yet applied).
   Would need write-tests to verify these still hold on fw 4.33.
3. **DMPAFT archive-page CRC comparison** — the archive pages might
   have subtly different byte layouts if fw 4.33 stores extra sensor
   values (solar/UV are both present on this bench Vue).
4. **RXTEST behavior** — deliberately skipped because it disrupts
   reception mid-audit; worth running in isolation later.
5. **Live production-Vue capture** for the specific departures found
   in this report.  Requires stopping `kanfei-logger` briefly (~5 min
   of prod downtime) and is a separate, permissioned action.

## Reproduction

The audit was captured by
`scripts/vantage_wire_audit.py` (not in-repo; assembled ad-hoc during
this session).  If we want to re-run this on a future firmware, or
against the production console, we should package that script and add
it here.  Filed as a note; not blocking.

## Related

- `vantage_fw433_notes.md` — running notes on individual fw 4.33
  findings (this report is the batch snapshot)
- `vantage_dash_values.md` — sensor-value wire-vs-doc catalogue
- `vantage_serial_ref_v261.txt` — the Davis reference this audit
  compares against
- Issue #297 — bench Vue wire-analysis tracker
