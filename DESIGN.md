# Milo design system

This records the existing interface in `web/style.css`. Use these values when
extending the client; the app is a compact, readable mail workspace with a blue
accent, restrained borders and separate navigation, list and conversation panes.

## Typography

- Bundled variable Geist, weights 100–900, with Apple/Segoe UI system fallbacks.
- Root size 14 px, line height 1.5. Navigation and list sender/subject use 14 px;
  previews and action labels use 13 px; timestamps use 11 px.
- Message text uses 16 px with line height 1.8. Input text uses 15 px, 16 px on
  narrow screens. Conversation headings use 21–29 px and weight 620; the list
  heading uses 27 px and weight 650. Inline composer headings use 16 px.
- Email HTML preserves sender typography in an isolated, sanitized frame.

## Theme tokens

| Token | Light | Dark |
| --- | --- | --- |
| `--surface` | `#ffffff` | `#111b2e` |
| `--surface-alt` | `#f4f7fc` | `#0b1322` |
| `--text`, `--ink` | `#172033` | `#e5edf9` |
| `--muted` | `#617189` | `#a3b3cb` |
| `--purple` (existing name for blue accent) | `#2563eb` | `#60a5fa` |
| `--soft` | `#eaf2ff` | `#1b3151` |
| `--line` | `#dfe7f2` | `#27364d` |
| `--sidebar` | `#eef4ff` | `#0f1a2c` |

Account dots and avatar outlines use the account's chosen `--account-color`.
The dark theme uses `data-theme="dark"`; sender HTML retains its own white frame.

## Layout, spacing and shape

- Desktop shell: 224 px sidebar, 335–390 px list, flexible reader; 72 px topbar.
  At 1600 px and above, sidebar/list become 240/430 px.
- At 1120 px, sidebar/list become 190/330 px. At 900 px, the list and reader
  occupy the same pane; selection opens the reader with a back action. At 600 px,
  navigation is a 235 px drawer and the topbar is 58 px high.
- Common gaps are 7–14 px; section padding is 18–30 px. Desktop reader padding
  scales from 25 to 66 px; narrow reader padding is 24 px vertically, 16 px across.
- Buttons/fields use 7–10 px radii; thread cards and inline composition use 12 px.
  Thread cards have 14 px separation and 18 px internal padding (12–14 px mobile).
- Mail rows use approximately 130 px minimum height, a 34 px avatar and a 3 px
  selected accent edge. Text truncates rather than widening the layout.

## Components and interaction

- Primary actions are solid accent buttons; secondary actions have an accent
  label and subtle border. Reply, reply all and forwarding remain beside the
  conversation; reply composition follows the thread in an inline card.
- Pin, analysis sparks, sent/replied markers and thread counts sit together in
  the row marker area. Icons use current-color strokes with rounded joins.
- Closed thread messages show compact sender/time summaries. Opening one loads
  its body in place. Quotes stay collapsed until requested; HTML frames resize
  to content without changing sender formatting.
- Loading skeletons use `--line`/`--soft`, 14 px lines with 7 px radius, a 1.6 s
  shimmer and explicit download status. Background work never blocks local text
  input or immediate optimistic list changes.
- Focus rings are 3 px sky blue (`#38bdf8`) with 3 px offset. Forms use an accent
  border and translucent blue focus halo. Motion stops for reduced-motion users.
- Cached content renders immediately; refresh and missing offline content get
  explicit status text. Keep technical setup details out of ordinary mail flows.
