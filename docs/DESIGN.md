# Frontend design system

The UI follows the editorial reference in [DESIGN_REFERENCE.md](DESIGN_REFERENCE.md)
("serif analytics on warm paper"), adapted for an operational dashboard.

## Applied from the reference

| Pattern | Implementation |
|---|---|
| Serif display type at weight 400, italic phrase | `Source Serif 4` (self-hosted, substitute for Signifier) via the `.display` class; every page title has one italic phrase |
| Body sans with half-step weights | `Inter` variable (substitute for Söhne), weights 430/450/480/500 |
| Ink-black filled pill + ghost pill pair | `Button` primary/secondary, `pillPrimary` / `pillGhost` link styles |
| 24px soft cards, no shadow | `Card variant="mist"` / tinted tiles (`rounded-3xl`) |
| Floating product artifacts (20px radius, whisper shadow) | `Card variant="float"` — used for charts and data tables |
| Peach accent card with sienna ink, once per page | dashboard *Estimated savings* card (`variant="peach"`) |
| Sienna chart stroke | live-power line (`--line-live`) over a peach gradient wash |
| Ghost category tags | gray eyebrow labels above titles and sidebar groups |
| Inputs 16px radius, pills 9999px | `inputCls`, all buttons/badges/nav items |

## Deliberate deviation: more colour

The reference is ~97 % achromatic. By request, a warm **tint palette** was added (peach, sky,
sage, butter, rose, lilac — each a soft surface with same-hue ink, `.tint-*`). It colours metric
tiles, status pills, source badges, nav icons and room tiles while keeping the editorial feel.
Text inside tints uses the tint's ink colour, never a chart series colour.

## Data colours (validated)

Chart series use a separate palette checked with the dataviz validator (CVD separation, contrast):
light `#2a6fb0` / `#e0663a` / `#3f9e6d`, dark `#3d85d8` / `#dd6233` / `#2f9e69`. Status always
ships icon + label. Dark mode uses its own warm token set, not an automatic inversion.
