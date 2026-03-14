# Hardware Test Plan (Driver Work)

This is a lightweight plan for field testers validating new PWS driver work.

## Goal

Confirm each driver can:

1. connect reliably
2. produce valid live readings
3. keep running without drops
4. support expected setup/config actions

## Scope (Current PRs)

- `#3` Vantage Pro/Pro2/Vue serial driver
- `#5` Ecowitt/Fine Offset LAN driver (on hold pending hardware testing)

## Tester Prerequisites

- Test station model + firmware version
- Connection method details:
  - serial adapter chipset/cable (for Vantage)
  - station IP/network details (for Ecowitt)
- Host OS + version
- Fresh checkout of the PR branch under test

## Execution Format

For each PR branch:

1. Check out branch
2. Run `python station.py setup`
3. Run `python station.py run`
4. Execute the checklist below
5. Record results in the report template

## Core Checklist (All Drivers)

### A. Setup and Detection

- [ ] Setup wizard can complete without errors
- [ ] Station can be probed/detected from setup flow
- [ ] `/api/station` reports `connected: true`
- [ ] Station type/name shown matches actual hardware

### B. Live Data Validity

- [ ] Dashboard updates at expected poll cadence
- [ ] `/api/current` timestamp advances continuously
- [ ] Temperature/humidity/barometer values are plausible
- [ ] Wind direction/speed values are plausible (including calm)
- [ ] Rain fields do not show impossible jumps

### C. Stability (30-minute run)

- [ ] No disconnect loops
- [ ] No repeated timeout/CRC spam in logs
- [ ] WebSocket updates continue for full run
- [ ] UI remains responsive

### D. Station/Driver Controls

- [ ] Reconnect from setup/settings works
- [ ] Read station config works (if supported by driver)
- [ ] Write station config works (if supported by driver)
- [ ] Clock sync works (if supported by driver)

### E. Regression Safety

- [ ] History page still loads data
- [ ] Forecast/Astronomy pages still function
- [ ] Enabling/disabling nowcast/spray still works

## Driver-Specific Notes

### PR #3 (Vantage Serial)

- [ ] Wakeup/handshake is reliable after cold start
- [ ] LOOP decoding looks correct across supported sensors
- [ ] Archive sync does not stall polling
- [ ] Reconnect behavior is reliable after USB unplug/replug

### PR #5 (Ecowitt LAN)

- [ ] Station reachable by IP/port from host
- [ ] Polling survives brief network interruption and recovers
- [ ] Field mapping appears correct vs station console/app
- [ ] Setup flow for non-serial station path is clear

## Pass Criteria

- No blocker defects
- All Core Checklist items pass, except explicitly unsupported driver features
- Any medium/low issues documented with reproduction steps

## Defect Severity

- **Blocker**: Cannot connect/poll, or data clearly invalid
- **Major**: Frequent disconnects, key sensors wrong/missing
- **Minor**: Intermittent UI/setup friction, non-critical mismatch

## Report Template (Copy/Paste)

```text
PR: #<number>
Driver: <vantage|ecowitt>
Tester: <name>
Date:
Host OS:
Station model:
Firmware:
Connection details:

Result: <PASS|PASS WITH ISSUES|FAIL>

Checklist:
- A Setup/Detection:
- B Live Data:
- C Stability:
- D Controls:
- E Regression:

Issues:
1) <severity> - <summary>
   Steps:
   Expected:
   Actual:
   Logs/screenshots:

Notes:
```
