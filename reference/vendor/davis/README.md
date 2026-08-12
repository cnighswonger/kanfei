# Davis Instruments — vendor materials

**These files are property of Davis Instruments (or its successors) and
are NOT part of Kanfei's licensed source code.**  Kanfei is GPL v3;
the files under this directory are third-party vendor artifacts
included for archival reference of tooling that may or may not remain
publicly available from the manufacturer.

Do not treat anything here as "part of Kanfei" for licensing purposes.
If Davis (or a rights-successor) sends a takedown request for any
file in this directory, we comply.

## Contents

### `DirectFromPC_Vue_3_00.exe`

- **Purpose**: Davis's last publicly-released firmware update
  utility for the Vantage Vue Console (Model 6250).  Flashes the
  console over the serial link to firmware v3.00.
- **Origin**: downloaded directly from Davis's official website
  (page URL not preserved at time of archival — Davis has been
  restructuring their support pages).
- **SHA-256**: `4c7ecdce4ce302c06a358c795a9ac15778cc7a86ce0e09199e6d160a3e3f2de5`
- **Size**: 417 KiB
- **Platform**: Windows PE32 executable (Intel 80386, GUI).
  **Windows-only.**  Davis does not provide a Linux/macOS version.
- **Preserved because**: per Davis's own KB documentation, Vue
  Console firmware updates for versions above v3.00 have never been
  released to end-users — post-MB hardware ships factory-flashed
  with 4.x firmware and there is no user-facing update path.  So
  v3.00 is the ceiling for anyone running a pre-MB Vue.  If Davis
  stops hosting this executable, this may be the only way to
  update a pre-MB console.

**HARD DO-NOT**s:

1. **Do NOT** run this utility on a Vue Console of hardware revision
   MB or later.  MB-and-later hardware shipped with 4.x firmware;
   trying to flash it back to 3.x will (per Davis KB) stop the
   WeatherLink datalogger from working, i.e. permanently damage the
   installation.  Serial-number decoding does not by itself tell
   you the hardware revision — check the console's own sticker for
   the letter code before running this.
2. **Do NOT** run this utility under WINE, Proton, or any other
   Windows-compatibility layer on Linux/macOS.  Firmware flashing
   with imperfect USB serial handling has a high probability of
   bricking the console mid-flash.  Use a real Windows PC with
   real Davis-supplied USB-serial hardware.  This is Chris's
   explicit hazard flag (2026-08-12).
3. **Do NOT** interrupt the utility once it has begun writing.
   Power loss or serial-cable disconnect mid-flash on a Davis
   console typically produces an unrecoverable brick.

### Verification

Before running, verify the archived binary matches the SHA-256 above.

```
sha256sum DirectFromPC_Vue_3_00.exe
```

If the checksum differs, do not run the binary — obtain a fresh copy
from Davis directly (if still hosted) rather than trusting the
in-repo file.

## Why we archive vendor binaries here

Davis's tooling and reference materials are historically prone to
disappearing from their website without notice.  The Vantage protocol
reference existed as `techref.doc` for years and was silently replaced
by the newer `vantage_serial_ref_v261` PDF; the old firmware update
executables have been progressively removed as new hardware revisions
made them obsolete.  Archiving here means anyone with a copy of the
Kanfei repo can retrieve tooling for the pre-MB Vue Consoles they
already own, even if the vendor stops distributing.

This is an archival preservation stance, not an endorsement of
redistribution.  If a Davis rights-holder requests removal, we comply
without argument.
