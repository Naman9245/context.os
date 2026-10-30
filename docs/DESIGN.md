# ContextOS design

How ContextOS looks, why, and the rules for building new screens. The tokens
live in `frontend/src/index.css` and the shared components in
`frontend/src/components/ui.tsx`. Architecture is in
[ARCHITECTURE.md](ARCHITECTURE.md), plans in [PLAN.md](PLAN.md).

## 1. The idea

A student's semester, kept like a good binder: colourful dividers, big friendly
numbers, nothing grey or corporate. The style follows the reference chosen for
the app in October 2026: warm cream pages, chunky cards in saturated pastel
colours, extra-round corners, bold rounded type, pill buttons and a dark
navigation bar.

**The signature** is the Dashboard's "today" stack: coloured bands tucked under
one another like the tab dividers in a binder. Coral holds the date and
Khushi's greeting, paper what Khushi says, sun the files waiting to be
organised, pine the library. The Files page repeats the idea quietly: each
subject's header is tinted in that subject's colour, like a divider. The band
stack belongs to the Dashboard only; every other page stays calm.

## 2. Colour

| Token | Hex | Used for |
|---|---|---|
| `stone-100` (cream) | `#F7EFE2` | the page |
| `stone-50` (paper) | `#FFFBF4` | cards |
| `stone-900` (ink) | `#1E1C23` | text, the navigation, main buttons |
| `stone-500` | `#655B51` | secondary text |
| `coral` | `#E8614F` | the greeting band, your chat messages, late deadlines |
| `sun` | `#F6B940` | the active page in the nav, Khushi, files to organise, due dates |
| `pine` | `#2E6B62` | the library |
| `lilac` | `#A898F2` | progress (phase 04) |
| `tangerine` | `#F39A48` | spare, for a future feature |
| `butter`, `blush`, `mint`, `haze`, `peach` | `#FCE7B5`, `#F9D5D0`, `#D3E8DF`, `#E7E1FD`, `#FDDCBB` | soft tiles, Khushi's speech bubble |
| `accent` | `#B53B2A`, `#F08A78` in dark mode | links, focus rings, checkboxes and sliders |

Tailwind's own `stone`, `amber`, `emerald` and `red` scales are re-tuned in
`index.css`: stone runs from paper to ink, amber is the sun, emerald the pine,
red the coral. So the status colours (warn, good, bad) belong to the palette;
use them for status only.

Rules:

- Text on a colour card is ink; on pine and ink it is paper. Coral is never used
  for small text: use `text-accent`, a coral dark enough to read.
- Every text and background pair meets WCAG AA (4.5:1). 23 pairs were checked
  in both themes on 30 October 2026, the lowest at 4.77:1. Check any new pair
  before using it.
- Dark mode needs no extra work in most places: the page becomes `#141318`,
  cards `#1E1C23`, colour cards keep their colours, the main button turns sun,
  and `stone-400`, `stone-500` and `accent` lighten by themselves.

## 3. Type

- **Gabarito** (display) for page titles (`font-display text-4xl sm:text-5xl
  font-extrabold tracking-tight`), card headings (`text-2xl font-extrabold`)
  and big numbers (with `tabular-nums`).
- **Figtree** for everything else.
- Both are bundled with the app (`@fontsource-variable/gabarito` and
  `@fontsource-variable/figtree`, 5.3.0), so they work offline and nothing is
  requested from Google.
- Small capital labels (`text-xs font-bold uppercase tracking-[0.14em]
  text-stone-500`) are rare: "Khushi says" is the only one so far.

## 4. Shape

- Cards `rounded-[28px]` with `p-5`; the Dashboard's bands `rounded-[32px]`;
  tiles `rounded-[20px]`; buttons, chips and badges are pills.
- Tailwind's radius scale is re-tuned too: `md` 14px, `lg` 20px, `xl` 24px,
  `2xl` 28px, `3xl` 36px.
- Flat surfaces. Only floating things get a shadow: the chat panel, Khushi's
  button and the navigation bar on phones.

## 5. Components

Paths are under `frontend/src/`.

| Component | Where | Use |
|---|---|---|
| `Card` | `components/ui.tsx` | `tone`: paper (default), coral, sun, pine, lilac, tangerine, ink, butter, blush, mint, haze, peach. `pad={false}` for lists that run edge to edge; do not override padding through `className`, because Tailwind does not let class order decide which class wins |
| `Button` | `components/ui.tsx` | `variant`: primary (ink; sun in dark mode), secondary (outlined paper), ghost, danger |
| `Badge` | `components/ui.tsx` | `tone`: neutral, good, warn, bad, accent |
| `Notice` | `components/ui.tsx` | `tone`: info, warn, bad |
| `ArrowCircle` | `components/ui.tsx` | the round arrow that marks something you can open; put it inside a link with the `group` class; `light` on pine and other dark backgrounds |
| `inputClass` | `components/ui.tsx` | rounded inputs with an accent focus ring |
| `KhushiAvatar` | `components/Khushi.tsx` | a sun circle with an ink "K" |
| `Page` | `components/Page.tsx` | each page's display title and subtitle |
| `Band` | `pages/Dashboard.tsx` | the signature stack; Dashboard only |
| icons | `components/icons.tsx` | 24px stroke icons drawn for the app, coloured by `currentColor` |

## 6. Layout

- Wide screens (768px and up): a dark rail on the left with the wordmark and
  the pages, icon and label; the current page sits on sun.
- Phones: the same links as a dark pill bar along the bottom, icons only (each
  has its label as its accessible name); Khushi's button floats above the bar.
- Content is at most 72rem wide (`max-w-6xl`). The Dashboard splits into two
  columns from 1024px.
- A grid holding truncated text needs `grid-cols-1` (`minmax(0, 1fr)`) on
  phones. Without it the column grows to the text's full width and the page
  scrolls sideways, as the Dashboard did at 375px before the fix.

## 7. Motion

One moment only: on the Dashboard the bands rise in one after another
(`animate-rise`, 80ms apart), and only under `motion-safe`. Links with an
arrow lift slightly on hover. Nothing else moves.

## 8. Accessibility

- AA contrast for all text (section 2).
- A visible focus ring: a 3px accent outline on `:focus-visible`.
- `prefers-reduced-motion` is respected.
- Decorative shapes (the preview bars, the arrows, the bullet dots) are
  `aria-hidden`.
- No sideways scrolling at 375px on any page (checked on 30 October 2026).

## 9. Building a new screen

1. Start from `Page` with a short title and a one-line subtitle.
2. Put content on paper cards. Give a colour card to the one or two things that
   matter most on the page, and keep each feature on its colour (section 2).
3. Show counts as big Gabarito numbers with a short label.
4. Put the main action on a primary button; at most one per area.
5. Before it is done: look at it in light and dark mode and at 375px wide, tab
   through it with the keyboard, and check the contrast of any new colour pair.
