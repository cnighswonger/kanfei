# Test Results - Validated Simulation Runs

This directory contains canonical "final validated" simulation runs for each historic tornado event tested with the V6 Enhanced nowcast system.

## Purpose

- **Reproducibility**: Reference outputs for regression testing
- **Baseline**: Known-good runs for comparing future prompt/algorithm changes
- **Documentation**: Training examples showing system behavior on real events
- **Validation**: Proof that features work correctly on diverse tornado scenarios

## Preserved Runs

### Moore EF5 Tornado (2013-05-20)
**File**: `moore_ef5_v6_validated.log` (593K)
- **Event**: Moore, OK EF5 tornado - 24 fatalities, $2B damage
- **Version**: V6 Enhanced (multi-meso tracking, motion vectors, hysteresis)
- **Date Run**: 2026-03-04
- **Features Validated**:
  - ✅ Single intense mesocyclone detection
  - ✅ Proximity-based threat scoring
  - ✅ Temporal tracking across cycles
  - ✅ EMERGENCY escalation on approach
  - ✅ Classic supercell signatures

### El Reno EF3 Tornado (2013-05-31)
**File**: `el_reno_ef3_v6_validated.log` (537K)
- **Event**: El Reno, OK EF3/EF5 tornado - widest tornado on record (2.6 miles)
- **Version**: V6 Enhanced
- **Date Run**: 2026-03-05
- **Features Validated**:
  - ✅ Multi-vortex mesocyclone tracking
  - ✅ High-precipitation supercell handling
  - ✅ Motion vector calculation (90-130 mph storm motion)
  - ✅ Statistical outlier detection (implausible speeds flagged)
  - ✅ Cycling behavior recognition

### Pilger Twin EF4 Tornadoes (2014-06-16)
**File**: `pilger_ef4_v6_validated.log` (542K)
- **Event**: Pilger, NE twin EF4 tornadoes - 2 fatalities, 75% town destruction
- **Version**: V6 Enhanced
- **Date Run**: 2026-03-06
- **Features Validated**:
  - ✅ Twin simultaneous tornado detection
  - ✅ Geographic diversity (Nebraska, KOAX radar vs KTLX)
  - ✅ Multi-mesocyclone tracking (12+ distinct mesocyclones)
  - ✅ RFD signature detection (temperature spikes/crashes)
  - ✅ Surface correlation (pressure drops, wind shifts)
  - ✅ Intelligent hysteresis (appropriate escalation/de-escalation)
  - ✅ Nighttime event handling

## Version History

- **V4**: Basic mesocyclone detection, fixed threat levels
- **V5**: Hysteresis, intelligent escalation, RFD detection
- **V6 Enhanced**: Multi-meso tracking, motion vectors, statistical QC, cycling detection

## File Format

Each `.log` file contains the complete simulation output including:
- All nowcast cycles (T-120 min through T+120 min)
- Full Claude analysis for each cycle
- Threat level evolution
- Mesocyclone detection details
- Surface observation correlations
- Radar analysis commentary

## Size Monitoring

**Current total**: 1.7M (3 files)
- If total exceeds 10M, switch to `.tar.gz` compression
- Expected compression ratio: ~10:1 (1.7M → ~170K compressed)

## Adding New Validated Runs

When adding a new canonical run:

1. Name format: `{event}_{intensity}_v{version}_validated.log`
2. Copy from /tmp or .test_cache to this directory
3. Update this README with event details
4. Commit to git: `git add test_results/` and create commit

## Exclusions

This directory is for **final validated runs only**, not:
- Debugging runs
- Failed/partial runs
- Intermediate development runs
- Bulk testing outputs

Use `.test_cache/` for ephemeral testing outputs.
