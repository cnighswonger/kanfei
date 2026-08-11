# Davis reference documents

Vendor documentation this project depends on.  **These are Davis
Instruments documents, reproduced here unmodified for offline
reference.**  They are not project documentation and should not be
edited — if something in them is wrong or unclear, note it in code
comments or an issue rather than changing the source text.

Two flavours of vendor doc live here:

- **Serial protocol references** cover the wire format the driver
  speaks — commands, packet layouts, EEPROM addresses.  Sections 1 and
  2 below.
- **User and installation manuals** cover the console setup menus and
  physical sensor mounting the operator sees.  Section 3 below.  These
  are the authoritative source for "which settings does the console
  actually expose" audits.

The two protocol families in sections 1 and 2 are distinct.  Confusing
them is a real hazard: see the "Address spaces" note below.

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

## 3. User and installation manuals

Vendor-facing operator manuals, distinct in purpose from the protocol
references above: these describe what the console shows on its LCD, the
setup menus the user walks through, and how the outdoor hardware is
physically installed.  They are the authoritative source when auditing
whether Kanfei surfaces every user-visible console setting.

| File | Contents |
|---|---|
| `vantage_vue_manual.pdf` | Vantage Vue Console Manual — setup wizard, console menus, alarms, calibration UI, graph modes |
| `vantage_vue_manual.txt` | Text extraction (`pdftotext -layout`) |
| `vantage_pro2_sensor_manual.pdf` | Vantage Pro2 & Pro2 Plus Integrated Sensor Suite (ISS) Installation Manual |
| `vantage_pro2_sensor_manual.txt` | Text extraction (`pdftotext -layout`) |

### Vantage Vue Console Manual

- **Document:** part number 07395.261, Rev. F, August 22, 2013
- **Covers:** Vue consoles #6351 and Vue weather stations #6250, #6357
- **SHA-256 (PDF):** `a97e209bf651f3cb88c2d02f90c585485bfb72ea7a30ad5f900e51a5bec0fc8f`

Use for: what settings the console UI exposes, what the LCD shows in
each screen, how alarms are configured, the console's own
calibration/offset UI (distinct from the CALED/CALFIX serial path).

### Vantage Pro2 ISS Installation Manual

- **Covers:** Vantage Pro2 & Pro2 Plus ISS (outdoor sensor suite)
- **SHA-256 (PDF):** `62a2d82f624189261adecd6f8f023a800aa19e98d1aa23e2734c602e56000abb`

Use for: physical sensor mounting, siting distances, cabling, and the
troubleshooting appendix for the ISS itself.  Not a protocol document
and largely orthogonal to the driver.
