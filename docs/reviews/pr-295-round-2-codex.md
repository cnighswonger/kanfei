# Review: PR #295 Davis reference manuals

Date: 2026-08-11
Reviewed: PR #295 at `0b4dd86d2e717739ae0f1346f3f110bcc0ad9360`
Round: 2
Label applied: `approved-by-codex-agent`, `reviewed-by-codex-agent`

## What Is Correct

- Verified `reference/vantage_vue_manual.pdf` SHA-256 matches the README: `a97e209bf651f3cb88c2d02f90c585485bfb72ea7a30ad5f900e51a5bec0fc8f`.
- Verified `reference/vantage_pro2_sensor_manual.pdf` SHA-256 matches the README: `62a2d82f624189261adecd6f8f023a800aa19e98d1aa23e2734c602e56000abb`.
- Regenerated both text extractions with `pdftotext -layout`; `cmp -s` matched the committed `.txt` files byte-for-byte.
- The README classification is accurate. The existing sections describe protocol references for wire commands, packets, and EEPROM/configuration semantics. The new section correctly identifies the Vue PDF as a console/user manual covering setup screens, alarms, graph modes, and calibration UI, and the Pro2 PDF as an ISS installation manual covering physical sensor mounting, cabling, siting, and troubleshooting.
- Legal/provenance check found only the expected Davis copyright/all-rights-reserved language and ordinary document/support contact information. I did not find any extra license, redistribution prohibition, embedded JavaScript, encryption, or other vendor-provenance surprise beyond the existing accepted vendor-reference posture. The omission of retrieval URLs for the new manuals is a known accepted scope call.

## Blockers

None.

## What Needs Attention

None.

## Bloat / Non-Functional

None. This is a docs/reference artifact addition with generated text extractions following the existing `reference/` convention.

## Recommendations

None required for this PR.

## Bottom Line

Approve. The committed binary manuals match the pinned hashes, their text extractions are reproducible with `pdftotext -layout`, and the README accurately separates protocol references from user and installation manuals. No code changed, so no code tests were applicable.

— Codex, cross-LLM review, round 2