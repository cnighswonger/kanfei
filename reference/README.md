# Davis protocol reference documents

Vendor documentation for the Davis serial protocols this project speaks.
**These are Davis Instruments documents, reproduced here unmodified for
offline reference.** They are not project documentation and should not be
edited — if something in them is wrong or unclear, note it in code comments
or an issue rather than changing the source text.

There are two distinct document sets, covering two distinct protocol
families. Confusing them is a real hazard: see the "Address spaces" note
below.

## 1. Legacy WeatherLink SDK (1999)

The original Davis "Sample Code and Programming Reference" disk.

| File | Contents |
|---|---|
| `techref.txt` / `.doc` | Protocol reference — commands, memory addresses |
| `appendix.txt` / `.doc` | Bar/power bits, model numbers, wind sectors, alarm bits |
| `database.txt` / `.doc` | WeatherLink database file formats |
| `faq.txt` / `.doc` | Programmer's FAQ |
| `readme.txt`, `readme.htm`, `index.html`, `license.htm` | Disk front matter |
| `serial.c`, `commands.c`, `ascii.c`, `ccitt.h`, `serial.h`, `thitable.h` | Davis sample C code |
| `comm.bas`, `form1.frm`, `form1.frx`, `vb_link.exe`, `vb_link.mak` | Davis sample VB code |
| `crc.dat` | CRC lookup table |

**Covers:** Monitor II, Weather Wizard II/III, Perception II, GroWeather,
Energy, Health.

**Does NOT cover Vantage.** `techref.txt` section IX lists memory addresses
only for the station families above; there is no Vantage section, and no
humidity-calibration entry anywhere in it. In this project these documents
back `backend/app/protocol/` (root) and `link_driver.py`.

## 2. Vantage Serial Communication Reference, Rev 2.6.1 (2013)

| File | Contents |
|---|---|
| `vantage_serial_ref_v261.pdf` | Original PDF, 60 pages |
| `vantage_serial_ref_v261.txt` | Text extraction (`pdftotext -layout`) |

- **Revision:** 2.6.1, March 29 2013
- **Covers:** Vantage Pro, Pro2, Pro Plus, Pro2 Plus, Vantage Vue
- **Retrieved:** 2026-07-29 from
  <https://oceancontrols.com.au/files/datasheet/ocean/VantageSerialProtocolDocs_v261.pdf>
- **SHA-256 (PDF):** `688aa6fb34d8135b2d10675f7c6527b176d310e8dc903d559ceec053df0c98ec`

This is the document cited in `backend/app/protocol/vantage/driver.py`'s
docstring, which was not previously in the tree. Its absence is the direct
cause of several address-map defects found during hardware validation
(issues #207, #208, #209) — the Vantage map had been transcribed without
access to the source.

Useful sections when working on `backend/app/protocol/vantage/`:

| Section | Topic |
|---|---|
| VIII | Command summary — the whole command set at a glance |
| IX | Command details (LOOP/LPS, DMPAFT, EEBRD/EEBWR, CALED/CALFIX, CLRCAL) |
| X.1–X.2 | LOOP and LOOP2 packet formats |
| X.4 | DMP / DMPAFT data format |
| X.6 | CALED and CALFIX data format |
| XII | CRC calculation |
| **XIII** | **EEPROM configuration settings** — the address map, including the calibration block at 0x32–0x4E |
| **XIV.1** | **Setting temperature and humidity calibration values** — the full five-step procedure |
| XIV.3 | Rain collector type |
| XIV.6 | Calculating ISS reception |
| XV–XVII | EEPROM graph data locations (Vantage Pro / VP2 / Vue) |

### Two traps worth knowing before editing the Vantage driver

**Address spaces.** The console has three memories, and the same number
means different things in each:

- **EEPROM** (4 KB) — calibration, lat/lon/elevation, config. Read/written
  with `EEBRD` / `EEBWR`.
- **Processor memory** (4 KB) — live sensor values, today's highs/lows.
  Not directly addressable; reached via `LOOP`/`LPS`, or `WRD` for a few
  fields.
- **Archive memory** (132 KB) — up to 2560 archive records, via `DMPAFT`.

Concretely: `0x4D` is `DIR_CAL` (wind direction calibration) in EEPROM,
*and* the station-type byte in processor memory. Issue #208 was caused by
exactly this collision — `0x12` was read as an EEPROM address when it was
actually the `WRD` command byte from `WRD 0x12 0x4D`.

**Calibration writes need more than EEBWR.** Per section XIV.1, a written
calibration offset does not take effect until the console receives a new
data packet for that sensor. The documented procedure is
`EEBRD` → `CALED` → compute un-calibrated values → `EEBWR` → `CALFIX`.
A bare `EEBWR` ACKs, reads back correctly, and silently does nothing —
which is what issue #209 was originally (mis)diagnosed from.
