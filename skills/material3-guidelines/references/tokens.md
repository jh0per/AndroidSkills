# Material 3 baseline values (orientation only)

The installed Compose Material3 defaults win over this table. Use these to sanity-check a design,
not to hard-code values in screens.

## Type scale (font size / line height, sp)

| Role | Large | Medium | Small |
|---|---|---|---|
| Display | 57 / 64 | 45 / 52 | 36 / 44 |
| Headline | 32 / 40 | 28 / 36 | 24 / 32 |
| Title | 22 / 28 | 16 / 24 (medium weight) | 14 / 20 (medium weight) |
| Body | 16 / 24 | 14 / 20 | 12 / 16 |
| Label | 14 / 20 (medium) | 12 / 16 (medium) | 11 / 16 (medium) |

```kotlin
val AppTypography = Typography().run {
    copy(
        displayLarge = displayLarge.copy(fontFamily = Brand), displayMedium = displayMedium.copy(fontFamily = Brand),
        // … apply to all 15 roles; change metrics only as a deliberate theme decision
    )
}
```

## Shape scale

| Token | Corner | Typical use |
|---|---|---|
| None | 0dp | full-bleed media |
| Extra small | 4dp | text fields (top corners), menus, snackbars, plain tooltips |
| Small | 8dp | chips, rich tooltips |
| Medium | 12dp | cards, small FAB |
| Large | 16dp | FAB, extended FAB, navigation drawer, side sheets |
| Extra large | 28dp | dialogs, bottom sheets (top corners), large FAB |
| Full | 50% | buttons, badges, search bar |

## Elevation levels

| Level | dp | Examples |
|---|---|---|
| 0 | 0 | most surfaces, filled/outlined cards |
| 1 | 1 | elevated card, modal sheet, banner |
| 2 | 3 | top app bar on scroll, menus, navigation bar |
| 3 | 6 | FAB, dialogs, search bar |
| 4 | 8 | hover/drag states |
| 5 | 12 | dragged items |

## Component sizes

| Component | Size |
|---|---|
| Touch target minimum | 48 × 48dp |
| Button height | 40dp (container), 48dp target |
| FAB / small / large | 56 / 40 / 96dp |
| Icon | 24dp |
| Navigation bar height | 80dp |
| Navigation rail width | 80dp |
| Small / medium / large top app bar | 64 / 112 / 152dp |
| List item (1/2/3-line) | 56 / 72 / 88dp min |
| Chip height | 32dp (48dp target) |

## Window size classes (width)

| Class | Width | Margins | Navigation |
|---|---|---|---|
| Compact | < 600dp | 16dp | navigation bar |
| Medium | 600–839dp | 24dp | navigation rail |
| Expanded | 840–1199dp | 24dp | rail or drawer |
| Large | 1200–1599dp | 24dp | drawer |
| Extra-large | ≥ 1600dp | 24dp | drawer |

Height classes: compact < 480dp, medium 480–899dp, expanded ≥ 900dp (landscape phones are
height-compact: avoid tall fixed headers there).

## Motion durations

| Token | ms |
|---|---|
| short1–4 | 50, 100, 150, 200 |
| medium1–4 | 250, 300, 350, 400 |
| long1–4 | 450, 500, 550, 600 |
| extra-long1–4 | 700, 800, 900, 1000 |

Emphasized easing for most transitions; standard easing for small utility motion.

## Contrast (WCAG)

| Content | Minimum ratio |
|---|---|
| Body text | 4.5 : 1 |
| Large text (≥ 18sp regular / 14sp bold) | 3 : 1 |
| Icons and component boundaries that convey meaning | 3 : 1 |

## Dependencies

```toml
androidx-compose-material3 = { module = "androidx.compose.material3:material3" }                         # via Compose BOM
androidx-compose-material3-adaptive = { module = "androidx.compose.material3.adaptive:adaptive" }
androidx-compose-material3-adaptive-layout = { module = "androidx.compose.material3.adaptive:adaptive-layout" }
androidx-compose-material3-adaptive-navigation = { module = "androidx.compose.material3.adaptive:adaptive-navigation" }
androidx-compose-material3-navigation-suite = { module = "androidx.compose.material3:material3-adaptive-navigation-suite" }
```

Compose Multiplatform: `compose.material3` from the Compose plugin and the JetBrains
`material3-adaptive` artifacts.
