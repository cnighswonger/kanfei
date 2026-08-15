# Image assets

Everything in `public/` drops into `frontend/public/` unchanged. Five files.

## Where each one is used

| File | Theme | Screen | Treatment |
|---|---|---|---|
| `about-hero.jpg` | dark / light | Sign-in, first-run, About | `cover`, `center 40%`, opacity `0.30` (auth cards) / `1.0` with a `rgba(10,13,20,0.42)` scrim (About) |
| `glaisher-adieu-1867.png` | glaisher | Sign-in, first-run | `cover`, `center 42%`, opacity `0.5`, `sepia(.62) contrast(1.02) saturate(.85)`, `mix-blend-mode: multiply` |
| `glaisher-adieu-1867.png` | glaisher | Spray Advisory | `contain`, `center 30%`, `no-repeat`, opacity `0.14`, same filter + multiply |
| `glaisher-flammarion.png` | mammoth | Spray Advisory | `contain`, `center 30%`, `no-repeat`, opacity `0.13`, same filter + multiply |
| `glaisher-ascent-1862.jpg` | glaisher | About, Dashboard | `cover`, opacity `0.34` (About, with a `rgba(237,226,196,0.34)` scrim) / `0.12` (Dashboard) |
| `glaisher-instruments.png` | glaisher / mammoth | Dashboard, Agriculture | corner plate, `contain`, `right bottom`, 400×280, opacity `0.09–0.10` |

Note `glaisher-adieu-1867.png` appears twice at different opacities — half-strength
behind an auth card, near-invisible behind a working screen.

## The two rules that matter

**1. Line engravings need `mix-blend-mode: multiply`.** These are ink on white
paper. Composited normally they wash the theme's ground toward white and read as
a photo; multiplied, the white drops out and only the ink lands, so the plate
behaves like it was printed on the same page. The dark theme's `about-hero.jpg`
is a photograph and does *not* use multiply.

**2. Theme backgrounds override user-selected ones.** The paper themes are
designed around these specific plates at these specific opacities. When a
`surface.texture` theme is active, the user's own background choice must be
suppressed and the picker disabled with a note explaining why — otherwise both
composite and the result is unreadable. See `themes/README.md`, "Background
ownership".

## Provenance

The four engravings come from `cnighswonger/kanfei-phone-sensor` (`frames/`) —
the same plates the Android app uses, so the two apps stay visually related.
`about-hero.jpg` is already in `frontend/public/` in the main repo.
