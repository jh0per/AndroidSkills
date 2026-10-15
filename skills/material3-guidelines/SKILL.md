---
name: material3-guidelines
description: Material Design 3 guidance for Compose apps - choosing the right component (buttons, FAB, app bars, navigation bar/rail/drawer, tabs, chips, dialogs, sheets, snackbars, menus, lists, cards), colour roles and dynamic colour, the type scale, shape and elevation scales, spacing and window size classes, canonical adaptive layouts, motion, and accessibility, mapped to Compose Material3 APIs. Use when designing or reviewing any screen, choosing a component, theming an app, or making a layout adaptive.
metadata:
  last-updated: '2026-10-15'
  keywords:
  - Material Design 3
  - components
  - colour roles
  - type scale
  - shape
  - window size classes
  - adaptive layout
  - motion
---

# Material 3 guidelines for Compose

Material supplies component anatomy, hierarchy, sizing, spacing and behaviour; the product supplies
brand roles. Start with the installed component and its defaults, then the theme. Callers pick
**roles**, never arbitrary measurements. A library upgrade does not silently approve a redesign.

Numbers here are Material 3 baseline values for orientation (see `references/tokens.md`); the
installed `androidx.compose.material3` defaults are the source of truth. Material 3 Expressive
(newer components and motion) is opt-in; adopt it deliberately, not piecemeal.

## Choose the component by job

### Actions

| Job | Component | Compose |
|---|---|---|
| The one most important action on a screen | Filled button, or FAB if it is the screen's primary creation action | `Button`, `FloatingActionButton` / `ExtendedFloatingActionButton` |
| Important but not primary | Filled tonal | `FilledTonalButton` |
| Secondary with clear boundary | Outlined | `OutlinedButton` |
| Low emphasis, inline, dialogs | Text | `TextButton` |
| Needs separation from a busy/patterned background | Elevated | `ElevatedButton` |
| Icon-only action | Icon button (standard/filled/tonal/outlined) | `IconButton`, `FilledIconButton`, … |
| Several related actions or a mutually exclusive choice of 2–5 | Segmented buttons | `SingleChoiceSegmentedButtonRow` / `MultiChoiceSegmentedButtonRow` |

One dominant action per surface. Destructive actions use the `error` role and a confirmation.
FAB: one per screen, for the primary *constructive* action; never for minor or destructive actions;
it sits above the navigation bar, bottom-end.

### Navigation

| Window width | Primary destinations (3–5) | Compose |
|---|---|---|
| Compact (< 600dp) | Navigation bar at the bottom | `NavigationBar` + `NavigationBarItem` |
| Medium (600–839dp) | Navigation rail | `NavigationRail` |
| Expanded+ (≥ 840dp) | Rail, or permanent/modal drawer for many destinations | `PermanentNavigationDrawer`, `ModalNavigationDrawer` |

`NavigationSuiteScaffold` (material3-adaptive-navigation-suite) switches bar/rail/drawer from the
window size automatically; prefer it for top-level navigation. Labels on bar items always; icons
alone are ambiguous. Selection uses the active indicator, not colour alone.

- **Top app bar:** `CenterAlignedTopAppBar` / `TopAppBar` (small), `MediumTopAppBar`,
  `LargeTopAppBar` for prominent titles that collapse on scroll with a
  `TopAppBarDefaults.exitUntilCollapsedScrollBehavior()`. Leading navigation icon, title, up to
  ~3 trailing actions, the rest in an overflow menu. A pushed screen always has a reachable back
  action.
- **Bottom app bar** (`BottomAppBar`): actions for the current screen, optionally with an embedded
  FAB; not a substitute for navigation.
- **Tabs:** switch between related panes of **one** screen at the same level. `PrimaryTabRow` /
  `PrimaryScrollableTabRow` under the top bar for main content groups; `SecondaryTabRow` inside
  content. Use the `Tab(text = …)` / `Tab(icon = …)` overloads so the 48dp layout applies. Fixed
  tabs split width equally; scrollable tabs size to content (use them for long or translated labels).
- **Search:** `SearchBar` / `DockedSearchBar`; results replace content, not a dialog.

### Selection and input

| Job | Component |
|---|---|
| Filter a set by tags/attributes | `FilterChip` (multi-select, shows check) |
| Choose one option inline from a few | `FilterChip` in single-select mode or segmented buttons |
| Suggested reply/action | `SuggestionChip`; `AssistChip` for contextual actions |
| User-entered items (recipients, tags) | `InputChip` |
| On/off setting applied immediately | `Switch` (in a `ListItem` with the label as the row) |
| Several options in a list, applied later | `Checkbox` |
| One of 2–5 visible options | `RadioButton` group, or segmented buttons |
| One of many | Exposed dropdown menu (`ExposedDropdownMenuBox`) |
| Value on a range | `Slider` / `RangeSlider` |
| Text | `OutlinedTextField` or `TextField` (one style per app), label always, supporting text for help and errors |
| Date / time | `DatePicker`/`DatePickerDialog`, `TimePicker` |

Text fields: show errors in supporting text with `isError = true`, keep the label visible, set
`keyboardOptions` (type, IME action) and `KeyboardActions`. Prefer inline fields or full-screen
forms to dialogs containing text input.

### Containment and lists

- `ListItem` (one-, two-, three-line) for settings and menus: leading icon/avatar, headline,
  supporting text, trailing control/meta.
- Cards (`Card`, `ElevatedCard`, `OutlinedCard`) group content about **one** subject; the whole card
  is one tap target or holds explicit actions, not both.
- `HorizontalDivider` sparingly; spacing separates groups better.
- Carousels (`HorizontalMultiBrowseCarousel`, `HorizontalUncontainedCarousel`) for browsing visual
  items.

### Communication

| Situation | Component |
|---|---|
| Brief confirmation of a completed action, optional undo | `Snackbar` via `SnackbarHostState` (one at a time, at most one action, no icons in text) |
| Information the person must act on, or that must persist | Inline banner/notice card in the content, not a snackbar |
| A decision that blocks progress (confirm delete, discard changes) | `AlertDialog`: title as a question/statement, body, confirm + dismiss text buttons, confirm on the end side |
| A complex task that needs focus on compact screens | Full-screen dialog |
| Supplementary content or actions tied to the screen | `ModalBottomSheet` (dismissible) or `BottomSheetScaffold` (standard) |
| Short-lived progress | `LinearProgressIndicator` / `CircularProgressIndicator`; determinate when progress is known |
| Count or status on an icon | `BadgedBox` + `Badge` |
| Brief label for an icon | `PlainTooltip` / `RichTooltip` via `TooltipBox` |
| Contextual list of actions | `DropdownMenu` |

Never stack dialogs. Dialog actions are verbs ("Delete", "Discard"), not "Yes/No".

## Colour

- Use **roles**: `primary/onPrimary`, `primaryContainer/onPrimaryContainer`, `secondary…`,
  `tertiary…`, `error…`, `surface/onSurface`, `onSurfaceVariant`, `outline`, `outlineVariant`,
  and the surface container tiers (`surfaceContainerLowest` … `surfaceContainerHighest`) for layered
  surfaces. Every `on*` role is the content colour for its pair; never put `primary` text on
  `primaryContainer`.
- Generate the full scheme from a seed colour (Material Theme Builder) for light **and** dark;
  fill every role your components read, or unfilled roles fall back to library purple.
- Dynamic colour (`dynamicLightColorScheme`/`dynamicDarkColorScheme`, API 31+) is a product
  decision. If the brand must stay fixed, do not enable it; if enabled, keep a static fallback.
- Elevation is expressed through surface container tiers (tonal), not shadows alone.
- Contrast: body text ≥ 4.5:1, large text and essential icons ≥ 3:1. Do not convey state by colour
  alone.
- Content colour: components inside a `Surface` get `LocalContentColor`; text drawn outside one must
  name its colour.

## Typography

Pick a role from the type scale (`MaterialTheme.typography.*`): display (hero numbers, rare),
headline (screen headers), title (app bar, section, card titles), body (paragraphs), label
(buttons, chips, tabs, captions). Do not invent sizes; adjust the theme instead. Apply the brand
font to all 15 roles in one `Typography(...)`. Text must scale with the system font size: use `sp`,
avoid fixed heights on text containers, and test at 200%.

## Shape and elevation

Shape scale: extra-small (4dp: text fields, menus, snackbars), small (8dp: chips), medium (12dp:
cards), large (16dp: FAB, navigation drawer, side sheets), extra-large (28dp: dialogs, bottom
sheets), full (pill: buttons, badges). Set it once in `Shapes(...)`; components pick their own slot.
Elevation levels 0–5; most surfaces are level 0–2. A screen never assigns its own radius or shadow
to a component family.

## Layout and spacing

- 4dp grid; 8dp increments for component spacing. Margins 16dp on compact, 24dp on medium and
  wider; gutters between panes 24dp.
- Touch targets ≥ 48×48dp even when the visual is smaller (`Modifier.minimumInteractiveComponentSize()`).
- Reading width: cap line length (~600–840dp content width) on wide windows instead of stretching
  text edge to edge.
- Edge-to-edge is the default (`enableEdgeToEdge()`); `Scaffold` passes `PaddingValues` that the
  content must apply once. Each surface owns its inset once (see `compose-ui-practices`).

### Window size classes and canonical layouts

```kotlin
val info = currentWindowAdaptiveInfo()
val widthClass = info.windowSizeClass   // compact / medium / expanded breakpoints at 600dp and 840dp
```

| Layout | When | Compose |
|---|---|---|
| Feed | browsing a collection | `LazyVerticalGrid(GridCells.Adaptive(minSize))`: more columns as width grows |
| List-detail | list with item details | `ListDetailPaneScaffold` (two panes on expanded, one on compact) |
| Supporting pane | main content + related tools | `SupportingPaneScaffold` |

Decide centrally which layout each screen uses; keep action order and meaning when tools move from
a side pane into a sheet on compact. Since `targetSdk` 36, orientation and resizability locks are
ignored on large screens: every screen must work in any aspect ratio.

## Motion

Use component-provided transitions and `MaterialTheme.motionScheme` (Expressive) or the standard
easing/duration tokens: short (50–200ms) for small state changes, medium (250–400ms) for expanding
surfaces, long (450–600ms) for full-screen transitions. Container transform/shared element for
list → detail (`SharedTransitionLayout`), fade-through between unrelated destinations. Respect the
system "remove animations" setting.

## Accessibility checklist

- Every interactive element has an accessible name; icon-only buttons set `contentDescription`;
  decorative images set `contentDescription = null`.
- Merge semantics for rows that act as one control (`Modifier.semantics(mergeDescendants = true)`,
  `toggleable` on the row, not on the inner switch).
- Headings marked with `semantics { heading() }`; custom controls expose `role` and `stateDescription`.
- Focus order follows reading order; dialogs and sheets trap focus and return it on close.
- Test with TalkBack, Switch Access/keyboard, 200% font, display size large, dark theme.

## Review questions for any screen

1. Is there exactly one primary action, and is it the right component?
2. Does every colour come from a role, every text from a type role, every radius from the shape scale?
3. Do the navigation component and layout adapt across compact/medium/expanded?
4. Are all targets ≥ 48dp and labelled?
5. Does each surface own its insets exactly once, and is the back action always reachable?
6. Would a problem shown here disappear before the person can act on it (snackbar misuse)?
