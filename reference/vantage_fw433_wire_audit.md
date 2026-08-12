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
- **5 undocumented commands enumerated**.  Cross-check on the
  production Vue (fw 2.12) verified `OPMODE` and `IDENT` work
  identically on the older firmware, so those are NOT fw 4.33
  additions — Davis has had this factory-mode command set since
  at least 2009; it's simply undocumented in the Serial
  Communication Reference.  `OPMODE` is a safe read-only view of
  radio state + per-unit crystal cal; `IDENT` returns the product
  SKU.  `RESET` works but is more consequential than it looks
  on the wire — it puts the console into the initial-setup wizard
  on the LCD and clears the RTC, so it is NOT a "clean soft-reset"
  and should not be wired into the driver.  `GETREG` is gated
  behind test-mode entry that `TST 1` alone is not sufficient to
  activate — real access sequence unknown.  `HELP` is
  interactive-menu output; useful only for discovering the rest.
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

**Undocumented in Davis reference.  Works on fw 2.12 and fw 4.33
identically** — verified by cross-check on the production Vue.

```
send:  IDENT\n
recv:  \n\r6351\n\r
```

Returns the Davis product number as a 4-character ASCII string,
prefixed and suffixed by `\n\r`.  Both our consoles report `6351`
(Vantage Vue Wireless with WeatherLink IP bundle).

**Potential driver use**: identify the specific product bundle at
connect time — useful for capabilities that vary by bundle (e.g.,
whether a WeatherLink IP logger is present) without inferring from
station_type_code alone.  Not adopting yet; noted for future
consideration.

### N2. `HELP` returns an engineering / radio-tuning menu

**Undocumented in Davis reference.**  Initial audit captured only
32 bytes because the probe used a fixed-size buffer; a follow-up
capture with a bigger buffer and read-until-silence timeout got the
full 526-byte response:

```
==================================================
 Radio Tuning Commands

 TST x       - Enter test mode
 OPMODE      - Show test settings
 TX x        - Configure transmit operation
 RX x        - Configure receive operation
 HOP x       - Configure hop mode
 CHAN x      - Set radio channel
 DOM x       - Set radio domain
 BAND x      - Set radio band
 XTLCAL x    - Set freq crystal cal number
 SVTST       - Save test operation mode
 SETREG x y  - Set radio register x to value y
 GETREG (x)  - Get radio register value
 RESET       - Reset console
 SETPOW x    - Set radio power
```

`HELP 2`, `HELP ALL`, `HELP RADIO` all return the same page — no
sub-menus.

This is a **factory-mode / engineering command set** — access to
the console's radio silicon for tuning and diagnostics.  Almost
every command here is destructive or reception-disrupting; only
`OPMODE` and (arguably) `RESET` are candidates for driver use.

### N3. `OPMODE` returns runtime radio state (READ-ONLY, safe)

**Undocumented in Davis reference.  Works on fw 2.12 and fw 4.33
identically** — verified by cross-check on the production Vue.
Reveals radio configuration and per-unit calibration parameters
without needing to enter test mode.

Comparison of both consoles:

| Field | Prod (fw 2.12) | Bench (fw 4.33) | Interpretation |
|---|---|---|---|
| TST | 0 | 0 | test mode off |
| TX | 0 | 0 | not transmitting |
| RX | 0 | 0 | RX in default mode |
| HOP | 0 | 0 | |
| BAND | 0 | 0 | default US 902-928 MHz |
| CHAN | 0 | 0 | |
| DOM | 1 | 1 | radio domain 1 = US region (convention) |
| XTLCAL | 4 | 14 | per-unit factory crystal cal; NOT a drift value |
| TEMP | 741 | 746 | ambient (both consoles in same room) |
| TEMP CAL | -1 | -1 | same |

Return format is one ASCII field per line, colon-separated,
terminated by an empty `\n\r` line.

**Note on XTLCAL**: Initial theory was that XTLCAL might drift over
the 8-year age gap between the two consoles.  The cross-check
disproves that — it's the factory-baked per-unit crystal
calibration, unique to each console's radio silicon.  Not useful
for age or drift diagnostics.

### N4. `GETREG` requires test mode — entry sequence unknown

**Undocumented.**  `GETREG 0`, `GETREG (0)`, and bare `GETREG` all
return `\n\rNOT IN TEST STATE\n\r`.

**Follow-up attempt to enter test mode via `TST 1` was incomplete**:
sending `TST 1\n` returned `\n\rOK\n\r` (looks like an ACK), but a
subsequent `OPMODE` still reported `TST: 0` — so the test-mode
flag did NOT actually flip.  Subsequent `GETREG` calls continued to
return "NOT IN TEST STATE".

Also noted: `GETREG 1` (register index 1 specifically) returned
just `\n\r` instead of the "NOT IN TEST STATE" string that
`GETREG 0` and `GETREG 2..15` returned.  Register 1 may be
special-cased for something (broadcast frequency? crystal? unknown).

Real entry sequence unknown — probably requires an additional
command (e.g., write a "test enable" register first, or a specific
`TST x` argument other than `1`).  Would need Davis factory
documentation or reverse-engineering; not attempted further.

### N5. `RESET` — full reboot to setup-wizard state.  DO NOT USE FROM DRIVER.

**Undocumented; verified on fw 4.33.**  Sending `RESET\n` returns
`\n\rOK` plus 3 bytes of what appears to be reset-init binary; the
console then reboots.

Initial read of the wire suggested this was a clean soft-reset with
runtime state cleared and EEPROM preserved.  A follow-up check with
Chris looking at the front panel revealed it is **harsher than
that**.  Observed post-reset behaviour:

- Response on wire: `\n\rOK` + `2e 66 2e` (3 bytes, purpose unknown)
- Wire-visible reset window: ~5 sec until the response completes;
  another 3-8 sec until the console accepts a new wakeup ping
- **EEPROM settings preserved**: location, archive_period,
  RAIN_SEASON_START, SETUP_BITS, USE_TX, STATION_LIST all readable
  and correct post-reset
- **Runtime state cleared, including the RTC**: post-reset
  `async_read_station_time` returned an earlier time than we had
  set; had to re-run `async_write_station_time` to bring the clock
  back
- **OPMODE `TEMP` field cleared**: `746` pre-reset → `0` post-reset;
  the sensor read takes a moment to re-populate
- **Console enters the initial-setup wizard on the front panel LCD**
  after reset — the same wizard a factory-fresh or battery-swapped
  console would show
- **ISS pairing survives** — `USE_TX` and `STATION_LIST` are
  preserved in EEPROM, and once the operator dismisses the front-
  panel setup wizard the console re-locks onto the ISS within
  ~5-15 seconds (RXCHECK went 0 → 4 → 15 consecutive packets over
  ~30 sec)

**Driver-use verdict: DO NOT use this command from the driver.**

- Any RESET from the daemon would put an unattended production
  console into setup-wizard mode.  Even if the wizard is dismissible
  from the wire (unknown — not tested), the operator would see an
  unexpected "welcome to your Vantage" screen on their dashboard.
- Clock loss requires a re-write; if the daemon does not follow up
  in time the archive timestamps drift.
- Momentary ISS lock loss produces a spurious "outside sensors
  offline" gap in the data — the exact class of glitch Kanfei goes
  out of its way to avoid.

There is no legitimate driver-side use of RESET.  If a stuck state
ever wants recovery, the answer is a targeted `WRD` (wakeup) burst
or, in extremis, a service restart — not RESET.  Document its
existence for completeness; do not wire it into automation.

### Original N2 note (pre-follow-up capture)

The initial audit script probe reported HELP as returning only 32
bytes.  That was an artefact of the fixed-buffer receive.  Any
future audit tooling should read-until-silence rather than
fixed-length, or the same undersizing bug will recur on any command
whose response is longer than the caller guessed.

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
6. **`RESET` behavior** — verify it does what it says (soft
   re-init) without state loss; if clean, it replaces the
   battery-pull workflow for post-flash reinit.  Wants Chris's
   approval before first invocation.
7. **`GETREG`-behind-`TST`** — inspect radio chip registers to
   understand what silicon fw 4.33 talks to.  Would require the
   `TST 1` → `GETREG` → exit-test sequence and would disrupt
   reception during the test.
8. **`OPMODE` on production Vue** — capture the per-unit
   `XTLCAL` value from fw 2.12 for comparison; may reveal factory
   crystal-cal drift over time.  Read-only, no test-mode entry
   required, so could be done via a brief kanfei-logger pause.

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
