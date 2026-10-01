# Review: PR #558 — Zambretti + pressure-trend pressure-unit fix

Date: 2026-10-01
Reviewed: PR #558 at `d83af47a07c14cfe77c5c655acdd3cdfb31180db`
Round: 1
Label applied: changes-requested

## What Is Correct

The production conversion is correct. `SensorReadingModel.barometer` is canonically tenths of hPa: the live poller multiplies the SI hPa snapshot by 10, archive sync converts Davis thousandths-inHg with `inhg_thousandths_to_hpa_tenths`, and DMPAFT catch-up applies its tenths scaler before insertion. Relay backfill preserves the already-canonical stored representation, while database compaction only averages values in that same unit. I found no production writer that creates mixed-unit rows.

The two changed consumers do require thousandths of inHg. Converting both endpoints before subtraction preserves the unit expected by the trend thresholds, and converting the latest reading fixes Zambretti's erroneous low clamp. The conversion's maximum rounding error is below 0.5 thousandth inHg. Around the clamp boundaries, the tenths-hPa storage grid maps to 28.048/28.051 and 30.998/31.001 inHg; it does not introduce a conversion error large enough to create an unexpected clamp crossing.

The audit of other barometer-column readers found no additional instance of this bug. Those sites either use `sensor_meta.convert`, explicitly divide tenths-hPa into hPa, aggregate values without changing units, or deliberately preserve the canonical raw representation for another storage-scale consumer. The known-clean current, public-data, and CWOP paths remain correct.

The full backend suite passed: 1,588 tests, with 7 pre-existing deprecation warnings. `py_compile` also passed for both modified production modules and the new test module.

## Blockers

1. The new regression suite does not exercise either changed production caller. Every test in `tests/backend/test_zambretti_pressure_unit.py` invokes `hpa_tenths_to_inhg_thousandths` itself and then calls the downstream algorithm. If both conversions are removed from `backend/app/api/forecast.py:54` and `backend/app/services/poller.py:444`, all six tests still pass. This directly contradicts the suite's stated purpose of failing when a future edit drops either conversion. Add one test that drives `get_forecast` from tenths-hPa database rows and one that drives `Poller._get_pressure_trend` from tenths-hPa query results. These may mock the downstream algorithms and assert their received thousandths-inHg arguments, or assert stable caller-level outcomes. The tests must fail against the pre-fix caller code.

## What Needs Attention

- `tests/backend/test_zambretti_pressure_unit.py:82` is a brittle negative control. Its exact last-index assertion couples the test to `PRESSURE_LOW`, the normalization formula, and the steady table length while testing behavior that the production caller should never request. Replace it with the caller-level regression tests above. If a negative control is retained, assert only the stable symptom that distinguishes converted from raw input, not a specific table index.
- The strict threshold behavior is confirmed: converted pressure changes of exactly `20` exist on the tenths-hPa storage grid, and `analyze_pressure_trend` classifies both `+20` and `-20` as `steady`; only values beyond those bounds are rising/falling. Add a compact boundary test for `20`, `21`, `-20`, and `-21` while revising this suite so the intentional `>`/`<` contract cannot drift unnoticed.
- `backend/app/services/poller.py:444` does not need a function-local import. `utils.units` is a standalone conversion module and introduces no circular dependency here; move `hpa_tenths_to_inhg_thousandths` to the module imports. The explanatory comments in both callers are also much longer than the non-obvious invariant requires. A concise note that storage is tenths-hPa and the algorithm expects thousandths-inHg would preserve the useful reason without duplicating module documentation.

## Bloat / Non-Functional

The existing-file additions do not trigger the add/delete review threshold. The 149-line test file is new and excluded from that heuristic, but it is materially verbose for six algorithm-level assertions and still omits coverage of the changed callers. Replacing duplicated setup and long docstrings with focused caller regressions should reduce the file while improving protection.

## Recommendations

Add caller-level tests first, then remove or weaken the raw-input negative control and add the exact-threshold cases. Move the poller conversion import to module scope and shorten the comments while touching those lines. No production algorithm or schema redesign is needed for this PR.

## Bottom Line

The diagnosis, canonical unit, conversion helper, and production changes are sound, and no additional barometer reader needs the same fix. Revise the tests before merge: as written, they demonstrate that conversion plus each algorithm works, but they cannot detect regression of either line this PR actually changes.

— Codex, cross-LLM review, round 1
