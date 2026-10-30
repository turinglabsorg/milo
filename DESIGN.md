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
- Analysis sparks and pins sit in the sender header beside the time; account
  color is shown by the avatar outline, without a duplicate dot in the row.
  The sent/replied label follows the preview. Icons use current-color strokes
  with rounded joins.
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
- **Scarica posta ora** in the toolbar checks connected mail providers immediately,
  as do app entry and foreground activation. iOS pull-to-refresh uses the same
  action. Cached mail remains readable while the check runs; iOS shows
  **Controllo la posta…** and disables its download button until the check finishes.
- List headers show only the folder title and, for the inbox, a compact Recap
  action. Keep mailbox counts in navigation; never present the loaded list limit
  as the mailbox total. No date eyebrow, introductory copy or separate recap card.
- The account section starts with an explicit All accounts filter; choosing a
  named account filters that mailbox, and All accounts restores the unified list.
- Backspace/Delete trash the selected conversation; P toggles favorites. Show
  these shortcuts in toolbar tooltips and accessible shortcut attributes. Ignore
  typing, open editors/dialogs, composing input, modifier chords and held-key
  repeats; shortcuts also work while focused on rendered email HTML.

- Account connection actions form a full-width vertical stack with equal heights
  (42 px desktop, 44 px mobile). The Google action includes the multicolor G on a
  small white plate; IMAP/iCloud uses the same width and a secondary border.
- The sidebar has no AI promotional card. Identity is a settings tab using the
  existing form fields, with editable name, aliases, context and reply language.
- Recap views show a compact timestamp/status, unboxed high-contrast overview and
  a bordered list of numbered priorities. Numbers use a fixed 22 px column;
  source and model metadata stay subordinate. No lavender recap background.

- Ordinary mailbox edits confirm after a device-local journal write, without
  waiting for HTTP. Folder/account/search navigation projects the local catalogue;
  refreshes stay in background. Keep pending changes visible in the existing
  compact synchronization status. Rejected changes show a retry instruction;
  unrelated edits continue. Closing or saving a draft confirms device persistence.

## Daily-use features

- `--danger` (`#c0262d` light, `#f87171` dark) is reserved for destructive or
  blocking actions: `.secondary.danger` outlines, `.primary.danger-solid` for
  the confirming button of a destructive dialog. Never use it decoratively.
- Toasts may carry one action (`toast(text,{label,run,duration})`), e.g.
  **Annulla** for undo send (10 s) and completed to-dos.
- Navigation adds **Da fare** after the inbox and, when the screener is on,
  **Nuovi mittenti**; both use the standard count badge.
- To-do rows: 22 px square check (8 px radius family), 14 px task text, 12 px
  muted meta line; follow-ups carry a danger-tinted "Da seguire" tag.
  **Seleziona tutte** uses the list-header button. Selected rows use the bulk
  language (`--soft`, 3 px accent edge) and the bar’s **Fatte** marks them done.
  The check on a single row still completes only that row. The same selection
  lives on iOS: Seleziona, Tutte, Fatte.
- AI action items stay in the reader under **Da fare proposti** until explicitly
  accepted. Each row pairs the action text with **Accetta da fare**, a compact
  surface button with an accent label and 8 px radius. Accepted rows show a
  quiet check and **Nei da fare**; completed rows show **Fatto**. On narrow
  screens the control sits below the text. Only accepted actions enter the
  **Da fare** navigation list and its count.
- Ask Milo’s reply is only the answer text, in a bubble as tight as the
  question (8 px padding, 14 px, line-height 1.4). Cited mail sits underneath
  as a 12 px muted line, not inside the bubble.
- Bulk selection uses the selected-row language: `--soft` background, 3 px
  accent edge, accent avatar outline, and a sticky bar of icon actions.
- The list header stays title + Recap; Ask (question bubble) and the command
  palette (keyboard) live in the topbar as icon buttons.
- Compose To and Cc fields suggest people under the input: a surface list with
  an 8 px radius, `--line` border and a quiet shadow. Each row is the name at
  14 px and the address at 12 px in `--muted`. The active row uses `--soft`
  and the accent on the name. Arrow keys move, Enter accepts, Escape closes
  the list without closing the draft.
- Compose tools sit between body and actions: saved replies select and the
  "Ricordamelo se non risponde" follow-up select, both 13 px on `--surface-alt`.
  Scheduling opens a dialog of preset cards (label + muted date) plus a
  datetime field.
- Reader: VIP (crown) and Block (ban) follow a separator in the toolbar;
  Unsubscribe is a small bordered button before the subject that turns
  danger-coloured on hover. Quick replies are 16 px-radius pills under the
  reply actions, loaded on request.
- Shortcuts are listed with `kbd` chips (11 px, bordered, `--surface-alt`).
- The composer's message header pairs the **Messaggio** label with a segmented
  **Testo semplice / Formattato** control (8 px radius, selected = `--soft` with
  accent label). Formatted drafts show only the rendered HTML in a bordered
  editor (9 px radius) on a white frame; **Modifica** reveals a compact
  toolbar (30 px buttons, 36 px on mobile) and an accent focus border, and
  becomes **Fine**. An 11 px muted note says remote images are blocked, with a
  **Carica immagini** text button. iOS mirrors this with a segmented picker, a
  rendered web view and a toolbar shown while editing.
