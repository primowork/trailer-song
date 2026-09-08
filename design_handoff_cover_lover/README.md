# Handoff: COVER LOVER — UI redesign of trailer-song

## Overview
`primowork/trailer-song` is a Streamlit app (Hebrew, RTL) that finds cover versions of a song and ranks them by measured audio "bigness" (loudness/intensity) plus trailer signals, so a trailer editor can find a version worth cutting to. The product logic is good; the UI is a data tool. This handoff contains a redesign — renamed **COVER LOVER**, English UI, LTR, responsive (mobile + desktop from one design) — in three alternative directions, plus a faithful recreation of the current Streamlit screen for before/after comparison.

Decision context: the ceiling in Streamlit is real (full page rerun per interaction, columns that stack instead of shrink on mobile, unstylable widget internals). Direction 1a is implementable-ish inside Streamlit with heavy CSS; 1b and 1c effectively require a real frontend (React/Next + Tailwind) over the Python logic exposed as an API (`search.py`, `covers.py`, `suggest.py`, `classics.py`, `taste.py`, `audio.py`).

## About the Design Files
The files in this bundle are **design references created in HTML** — prototypes of intended look and behavior, not production code to copy. The task is to **recreate these designs in the target codebase's environment** using its established patterns and libraries. If no frontend environment exists yet (today the UI is Streamlit only), pick the framework and implement there — recommendation: Next.js + Tailwind + shadcn/ui, with the existing Python modules exposed as a small FastAPI layer.

Note: `.dc.html` files open directly in a browser. They contain inline-styled markup plus a small logic class; read them as spec, not as source to port.

## Fidelity
**High-fidelity.** Colors, typography, spacing, radii and interaction states are final-intent values and can be lifted verbatim. Layout inside each card is the intended layout at that width. Album art, waveforms and the scatter data are placeholders (striped boxes / generated values) — real artwork URLs already come back from iTunes/Deezer in `search.py`, and real loudness scores come from `audio.py` + `components/audio_meter`.

## Design Tokens

### Color
| Token | Hex | Use |
| --- | --- | --- |
| ink | `#0A0B0F` | app background |
| ink-rail | `#101219` | left rail, player bar, side panels |
| surface | `#14161D` | cards, inputs |
| surface-raised | `#161A24` | active/playing row, stack card |
| surface-chip | `#1E2230` / `#252A38` | inactive play button / selected pill |
| border | `#1E2230` | hairlines, quiet card borders |
| border-strong | `#232838` / `#262B3A` | input and card borders |
| grid | `#171A22` | scatter grid lines |
| text | `#ECEEF3` | primary text |
| text-2 | `#C3C8D4` | secondary text, links |
| text-3 | `#8A91A3` | metadata |
| text-4 | `#9AA1B2` | mono micro-labels, keyboard hints (min 4.5:1) |
| text-5 | `#7B839A` | axis labels, placeholder captions |
| amber | `#FFB020` | primary action, "big/loud" tier, playing state |
| amber-tint | `rgba(255,176,32,.055)` | "trailer territory" band |
| amber-line | `rgba(255,176,32,.22–.35)` | band edge, sign-tag borders |
| coral | `#FF6B4A` | loved/heart |
| coral-bg | `rgba(255,107,74,.12)`, border `rgba(255,107,74,.45)` | loved button |

Amber and coral are the only accents. Amber is reserved for primary action and the "big" tier — never decoration on every row (this rule is inherited from the current app's `.streamlit/config.toml` reasoning and should be kept).

Loudness tier → color: `score >= 70 → #FFB020`, `40–69 → #C3C8D4`, `< 40 → #8A91A3`.

### Typography
- Display: **Bricolage Grotesque** 800, letter-spacing `-.015em` — page titles (26–34px), the loudness number (24–34px), the wordmark (12–13px, letter-spacing `.16em`, uppercase).
- UI: **Instrument Sans** 400/500/600 — body 12–15px, row title 14–14.5px/600, metadata 11.5–13px.
- Mono: **JetBrains Mono** 500 — micro-labels 9–11px, letter-spacing `.10–.14em`, uppercase; all numeric scores (tabular).
- Minimum text size 11.5px; touch targets on mobile 44px.

### Spacing / shape
Spacing: 2, 4, 6, 8, 10, 14, 18, 22, 26px. Radii: 5–6 (tags), 7–9 (art, small buttons), 10–12 (rows, inputs, cards), 14–18 (stack card, mobile cards), 50% (play/heart circles). Shadow: `0 18px 40px rgba(0,0,0,.5)` (stack card), `0 8px 24px rgba(255,176,32,.28)` (big amber play button).

## Screens / Views

### 0. `Current UI (Streamlit).dc.html` — before
Recreation of today's screen from `app.py` (lines 57–380 injected CSS, 771–970 sidebar, 1180–1510 cards + search bar, 1511–1947 panels/results) and `.streamlit/config.toml`. RTL Hebrew, background `#0B0D12`, sidebar `#14171F` on the right, 1180px content column, searchbar container `#14171F` / border `#2C3342` / radius 12 / padding 5, result cards `#14171F` radius 12 with 56px artwork, score badge, and a 32px amber circular play button. Use it only as the baseline.

### 1a. STUDIO (recommended default) — desktop 1080px + mobile 390px
**Purpose:** search a song, scan every cover, audition fast.
**Layout (desktop):** 210px left rail (`#101219`, right hairline) | fluid content column, padding 22/26px, and a player bar pinned to the bottom of the content column.
- Rail: wordmark (two lines, mono-spaced caps), nav items 13.5px in 8/10px pill rows — active `#1A1E29`; Loved shows an amber count; a "YOUR TASTE" block with a 12px/1.55 explanation of the learned profile; "RECENT" at the bottom.
- Search: single 12px-radius container, `#14161D` on `#232838`, 6px padding, 14px left inset — `⌕` glyph, free text input 15px, the resolved artist as a removable mono chip, ghost "Surprise me" (the dice roll from `roll_famous_song`), amber "Find covers" (32px tall, 600).
- Mode row: segmented pills in a 9px-radius shell (Covers of a song / Covers of an artist / Free search) on the left; Sort and "Filters · 2" as 8px-radius outlined selects on the right.
- Heading: `63 covers of Yellow` (Bricolage 26/800) + a 12.5px explanation line ("6 declare a trailer version · measured in your browser").
- Result row (48px tall content, 11/12px padding, radius 10): 48px art → 34px circular play → title block (artist 14.5/600, then `track · genre · year · duration` 12.5px `#8A91A3`) → sign tags (mono 10px amber outline: EPIC / TRAILER / CINEMATIC, from `search_module.trailer_indicators`) → **loudness meter**: 150px track, 6px tall, radius 3, fill = score% in the tier color, with the number in mono to its right → heart (32px, outlined; coral when loved) → `⋯` overflow. Playing row gets background `#161A24`, border `#2A3040`, amber play button.
- Player bar: 40px art, animated 4-bar equalizer (amber, `scaleY(.35→1)`, 0.9s ease-in-out, 0.15s stagger per bar), title + "30-second preview · full version on YouTube Music ↗", keyboard hints in mono on the right (`SPACE play · ↑↓ move · L love`).
**Mobile 390px:** same content, one column; search collapses to a summary field; modes become a horizontally scrolling pill row; the row becomes art + title/meta + meter on the left and a stacked 44px play / 44px heart on the right; player bar sticky at the bottom with a 3-bar equalizer.

### 1b. STACK — mobile 390px + desktop 860px
**Purpose:** audition one cover at a time; loving/skipping is what trains the taste model.
- Background: `radial-gradient(120% 55% at 50% 0%, #231A12 0%, #0A0B0F 62%)` (mobile) / `radial-gradient(80% 60% at 22% 0%, …)` (desktop).
- Header: wordmark + position counter (`3 / 63`) in mono.
- Context: mono `COVERS OF` label, then `Yellow` (Bricolage 22/800) with `Coldplay, 2000` in 15px `#8A91A3`.
- Card: radius 18, `#161A24` on `#262B3A`, 18px padding, big shadow; behind it a second card offset `translateY(14px) scale(.96)` at 55% opacity to imply the deck. Contents: square album art (radius 12) with a mono caption, artist 19/600, track 13px, meta 12.5px, loudness as a 34px Bricolage number in the tier color with a mono `LOUDNESS` label, sign tags, then a 44-bar waveform (2px gaps, `#2C3242`, heights from the measured envelope).
- Controls: 56px skip (`✕`, outlined) · 76px amber play with amber glow · 56px coral heart. Footer: hairline + `n loved from this song`.
- Desktop: same card unrolled into a 220px art + detail column, plus a 250px "UP NEXT" queue panel (`#101219`) listing the next four with fading opacity and their scores; keyboard hints `← skip · → love · SPACE play`.

### 1c. FIELD — desktop 900px + mobile 390px
**Purpose:** see the whole result set at once instead of scrolling a list; find the loud outliers.
- Plot area: height 340px (mobile 190px), radius 12, `#0E1016` on `#1E2230`. Grid: vertical lines every 12.5%, horizontal every 25%, color `#171A22`. Top 33% is the amber "TRAILER TERRITORY" band (`rgba(255,176,32,.055)` + dashed amber top edge, mono label at top-left).
- Axes: X = release year (labels 2000 / 2008 / 2014 / 2019 / 2024 in mono `#7B839A`), Y = loudness. Dot size = fit to taste: 22px (score ≥ 70), 16px (40–69), 11px (< 40); centered via a negative margin of half the size. Fill/ring: selected `#FFB020` / `#FFD489`; loud `rgba(255,176,32,.55)` / `.8`; quiet `rgba(195,200,212,.22)` / `.45`. Non-shortlisted covers render as `rgba(195,200,212,.12)` background dots.
- Right column: "SELECTED" card (56px art, title, meta, 40px amber play, 40px coral heart, 24px loudness number) and a "SHORTLIST · 4" list (7px tier dot + name + score).
- Bottom: filter pills (Verified same work / Orchestral / Fast action / Under 3:00 / Unheard only) — these map to the existing `filters` dict, `same_work_only` and `fresh_only`.
- Mobile: the field becomes a 190px strip above a selected card and a short shortlist.

## Interactions & Behavior
- **Play:** one shared audio element for the whole page (this is a hard requirement inherited from `app.py`: mobile Safari caps media elements per page, and one element makes "only one plays at a time" free). Clicking play on the active row toggles pause. A dead preview URL must render as a disabled/greyed play button, not a button that does nothing.
- **Love:** toggles instantly, no page reload, and feeds the taste profile (`taste.py`). Loved = coral fill. **Skip / thumbs-down:** trains away from that style; it must not remove the row from the results.
- **Ordering:** order is frozen while the user is browsing; newly learned signal is applied only when the user asks for it ("Re-sort — n tracks will move"), so the list never shifts mid-listen. Keep this behavior — it exists in `resort_button`.
- **Search modes:** Covers of a song (merged catalog + store search, with the "which work did you mean?" disambiguation when MusicBrainz returns several works) / Covers of an artist (top titles preview first, then a full scan) / Free search + filters.
- **Suggestions:** as-you-type completions from the real catalog plus the "did you mean" correction and the Hebrew-keyboard-layout fix (`suggest.py`) — in the new UI these are a dropdown under the field, not a row of buttons.
- **Animations:** equalizer bars 0.9s ease-in-out infinite, staggered 0.15s; card transitions in 1b should be a 220–280ms ease-out translate+fade; dot selection in 1c is an instant fill change plus a 1px ring. No page-level loading flashes — data loads per panel with skeletons.
- **Errors:** a failed store lookup must say so explicitly ("Search didn't complete: …"), never render as "no results" (this bug is documented in `_lookup_failed`).
- **Responsive:** one design; breakpoint at 768px. Below it: single column, no horizontal scroll, 44px minimum targets, the score/meter stays on the same line as the title.

## State Management
`query {title, artist}`, `mode`, `filters {style, tempo, length, recency, preferNew, freshOnly, sameWorkOnly}`, `workId` (chosen MusicBrainz work — must be invalidated whenever the query text changes), `results[]`, `displayOrder[]` (frozen), `visibleCount` (page size 20), `playingId`, `loved{}` (persisted), `rejected{}` (persisted), `blacklist[]` (persisted), `loudness{}` cache keyed by track, `seenKeys[]`, `selectedDot` / `cardIndex` for 1c / 1b, `tasteProfile`.
Data: search and cover-resolution endpoints from `covers.py`/`search.py`; loudness is measured **in the browser** (Web Audio `decodeAudioData` over the 30s preview) and cached by track key — keep the server-proxy fallback for CORS-blocked stores (`preview.py`).

## Assets
No real assets in the bundle. Album art is a striped placeholder (`repeating-linear-gradient(135deg,#1F242F 0 8px,#181C26 8px 16px)`) — swap in the artwork URLs already returned by iTunes/Deezer. Icons are text glyphs in the prototype; use the codebase's icon set (Lucide if you go with shadcn/ui) for play/pause, heart, thumbs-down, more, search, download, upload, sort. The wordmark is a 22px amber rounded square (radius 6) with a dark 50% circle inset 8px — a record, not a square; keep it or replace with real branding.

## Files
- `COVER LOVER.dc.html` — the three redesign directions (1a STUDIO, 1b STACK, 1c FIELD), desktop + mobile each. Live interactions: play toggle, love toggle, skip, dot selection.
- `Current UI (Streamlit).dc.html` — recreation of the existing Streamlit screen (before state).
- `screenshots/00-before-streamlit.png` — the current Streamlit screen.
- `screenshots/1a-studio.png`, `screenshots/1b-stack.png`, `screenshots/1c-field.png` — each direction, desktop + mobile side by side.
- Source of truth for behavior: `app.py`, `search.py`, `covers.py`, `suggest.py`, `taste.py`, `audio.py`, `classics.py`, `storage.py`, `components/audio_meter/index.html`, `.streamlit/config.toml` in `primowork/trailer-song@main`.

## Not designed yet
Loved/playlist screen, charts index, expanded filters panel, settings + Billboard import, and empty/onboarding states. They exist in the current app (sidebar and the two expanders) and are described above only as entry points.
