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
| `--surface` | `#ffffff` | `#000000` |
| `--surface-alt` | `#f4f7fc` | `#0d0d0d` |
| `--text`, `--ink` | `#172033` | `#f2f2f2` |
| `--muted` | `#617189` | `#a5a5a5` |
| `--purple` (existing name for blue accent) | `#2563eb` | `#60a5fa` |
| `--soft` | `#eaf2ff` | `#171717` |
| `--line` | `#dfe7f2` | `#272727` |
| `--sidebar` | `#eef4ff` | `#050505` |

Account dots and avatar outlines use the account's chosen `--account-color`.
The dark theme uses `data-theme="dark"`; sender HTML retains its own white frame.

## Layout, spacing and shape

- Desktop shell: 200 px sidebar, 320–360 px list, flexible reader; 58 px topbar.
  At 1600 px and above, sidebar/list become 210/370 px.
- At 1120 px, sidebar/list become 180/320 px. At 900 px, the list and reader
  occupy the same pane with a 54 px topbar. At 600 px, navigation is a 220 px
  drawer and the reader uses 18 px vertical/12 px horizontal padding.
- Common gaps are 6–12 px. Sections use 12–22 px padding. Dense mail rows use
  11 px vertical/16 px horizontal padding, approximately 92 px minimum height,
  a 30 px avatar and a 3 px selected accent edge.
- Buttons/fields use 8 px radii; thread cards and inline composition use 9 px.
  Thread cards have 9 px separation and 12–14 px padding. Modals use 18–20 px
  padding on desktop and 16 px on mobile. Text sizes stay readable.

## Components and interaction

- Primary actions are solid accent buttons; secondary actions have an accent
  label and subtle border. Reply, reply all and forwarding remain beside the
  conversation; reply composition follows the thread in an inline card.
- Pin, analysis sparks, sent/replied markers and thread counts sit together in
  the row marker area. Account dots, analysis sparks and pins sit in the sender
  header beside the time; the sent/replied label follows the preview. Icons use current-color strokes with rounded joins.
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

- Account connection actions form a full-width vertical stack with equal heights
  (42 px desktop, 44 px mobile). The Google action includes the multicolor G on a
  small white plate; IMAP/iCloud uses the same width and a secondary border.
- The sidebar has no AI promotional card. Identity is a settings tab using the
  existing form fields, with editable name, aliases, context and reply language.
- Recap views show a compact timestamp/status, unboxed high-contrast overview and
  a bordered list of numbered priorities. Numbers use a fixed 22 px column;
  source and model metadata stay subordinate. No lavender recap background.
