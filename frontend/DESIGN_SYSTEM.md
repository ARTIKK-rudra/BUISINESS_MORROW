# Morrow Business Command Center — Design System

## Product direction

Morrow is a premium business operating workspace organized around three questions: what is happening, what may happen next, and what deserves action. The current redesign follows the brief’s warm ivory and cream palette, compact navigation, blue-to-teal focal hero, calm KPI cards, and restrained editorial spacing.

## Reference interpretation

The supplied dashboard screenshots show several related analytics patterns: compact navigation, rounded white work surfaces, small KPI cards, chart-led layouts, clean tables, and blue, teal, mint, and lavender accents. One image establishes a warm neutral shell; another uses mint highlights; the others demonstrate cool blue accents and compact performance panels. The earlier user-provided CargoWave website video contributes a focal blue/teal hero and spacious section rhythm. These are visual references only; brand names, logos, and sample metrics are not reused.

The design resolves those references around the user's explicit Business Command Center direction: warm ivory canvas and cream sidebar, restrained blue/teal hero, editorial whitespace, and business-specific finance/operations content. It combines the screenshots' compact card and chart hierarchy with a persistent 22-destination application shell.

## Foundations and tokens

Central semantic tokens live in `src/app/reference.css`; existing structural rules remain in `src/app/globals.css`.

| Token family | Light theme | Dark theme |
| --- | --- | --- |
| Canvas | `#F8F7F2` | `#17191C` |
| Sidebar | `#F2F0E8` | `#202124` |
| Surface | `#FFFFFF` / `#FFFEFA` | `#202226` |
| Text | `#20242C` | `#E6E4DF` |
| Muted text | `#858990` | `#A8A9AB` |
| Border | `#E9E7DF` | `#36383B` |
| Primary | `#2563EB` | `#76A5FF` |
| Teal accent | `#0EA5A4` | `#54C1BB` |

Success, warning, danger, information, AI insight, prediction, risk, recommendation, and anomaly have separate semantic tokens. Inter is the primary font with Avenir/Segoe/system fallbacks. Cards use a 12px radius; controls use an 8px radius. Shadows are low contrast and reserved for separation.

## Hero media

- Opening hero video: `public/media/command-center-motion.mp4` (H.264 MP4, about 2.9 MiB, 17.76 seconds, 24 fps, 1280×720), optimized from the supplied [Pexels clip 40302723](https://www.pexels.com/video/40302723/).
- Second-slide food video: `public/media/menu-slide-motion.mp4` (user-provided iStock MP4, 768×432, about 3.8 MiB, 29.7 seconds) with a locally generated matching poster at `public/media/menu-slide-poster.jpg`. The ship footage remains in the opening hero only; this second slide now shows the provided food-preparation clip.
- Poster and static fallback: `public/media/command-center-poster.jpg`, extracted from the supplied clip.
- Pexels states its videos can be used for commercial projects and that attribution is not required ([Pexels license](https://www.pexels.com/license/)). The exact source URL is recorded here; no Pexels branding is used in the interface.
- Both `<video>` elements are muted, looping, inline, and use `object-fit: cover`; each plays only while its own slide is active. The hero keeps its blue-to-teal tint. Under `prefers-reduced-motion: reduce`, both videos are hidden and matching posters remain.
- No video is placed behind the rest of the dashboard or other routes.

## Application shell and reusable UI

- `components/shell.tsx`: fixed 258px cream navigation, grouped links, active route, desktop collapse, collapsed tooltips, mobile drawer, command palette (`Ctrl/Cmd+K`, arrows, Enter, Escape), theme switch, notification link, and sample-data status.
- Route content uses a restrained entrance transition and active sidebar markers animate into place. Dashboard KPI counters ease between selected sample periods; they respect reduced motion and expose the final value to assistive technology.
- Theme preference is applied before hydration to avoid an initial theme flash; theme and sidebar state persist in local storage.
- `components/ui.tsx` and `components/async-state.tsx`: shared headings, buttons, KPI cards, export/add unavailable states, and loading/success/empty/error/retry states.
- `components/charts.tsx`: Recharts styles for sales, profit, expenses, inventory, and forecast data.
- `features/workspace/preview-sections.tsx`: page-specific cards/timelines for shared-route screens.
- `mocks/business-preview.ts`, `lib/mock-data.ts`, and `lib/workspace-preview.ts` isolate demonstration records from `lib/api.ts`.

## Screen information architecture

Dedicated page components: Dashboard, Sales, POS, Inventory, Suppliers, Recommendations, Voice Assistant, Notifications, Analytics, Business Assistant, Invoice Capture, and authentication. The 14 remaining required screens use the shared route shell but each has its own page-specific section: orders/fulfillment, product catalog, purchase tracking, expenses, generated-ledger explanation, profit and loss, demand forecasts, AI findings, anomaly investigation, customer directory, employee roles, reports, settings tabs, and an audit timeline.

All demonstration values are identified by the workspace’s sample-data banner or page-specific preview labels. Mock operations never write to the application API. Purchase approval is unavailable in demo mode until a live quote and owner session can be checked.

## Responsive and accessible behavior

- Desktop: fixed grouped navigation and an aligned content workspace with a lead revenue window plus distinct profit, expense, and order surfaces.
- Tablet: reduced density, two-column KPI row, and single-column dashboard analytics where required.
- Mobile: compact top bar and drawer, stacked charts/cards, two-column KPIs, and horizontally scrollable dense tables.
- Tested dashboard widths: 1920, 1440, 1280, 1024, 768, 390, and 360 CSS pixels. All required routes were also rendered at 1440px and 390px.
- Semantic landmarks, skip link, visible focus styles, accessible labels, keyboard navigation, dialog names, reduced-motion handling, and explicit unavailable states are part of the shared baseline.

## Premium display window refinement

- The dashboard uses a large revenue display window with an illustrative trend line, separate profit / expense / order surfaces, and secondary margin and average-order-value context.
- Analytical chart windows, operational health, recommendation, and anomaly panels use different visual treatments while retaining the shared surface and spacing system.
- Shared route summaries, feature panels, and tables now use larger type, tabular financial numerals, deeper but restrained shadows, and responsive spacing.
- Light and dark themes have independent graphite/ivory surface depths. Dark forecast uncertainty uses a theme-appropriate muted blue band.
- Display windows gently scale on pointer hover or keyboard focus, with reduced-motion preferences disabling the scale transition and effect.
- The dashboard uses an eight-slide presentation: the original full-window hero occupies the opening screen, a separate centered capsule-video slide follows it, then a menu/billing slide, overview, performance, revenue, operations, and action slides replace one another in the same viewport.
- Wheel/trackpad scroll, touch swipes, Page Up/Down, arrow keys, the chapter controls, and dashboard chapter navigation switch slides. The outgoing slide fades and moves away as the next slide enters; the transition reverses when navigating upward. This keeps the dashboard as a presentation stage rather than a long stack of visible pages.
- Each slide is constrained to the available area below the persistent top bar. Responsive layouts keep important content within the stage; reduced-motion mode removes the slide animation.
- The menu slide uses the supplied restaurant-table photo as a full-slide background, positioned lower so both wine glasses and the table remain visible. Its desktop menu windows form a horizontally scrollable carousel with arrow controls, capped at 260px high and narrowed to reveal more of the background; mobile switches to a shorter 2×2 grid. Product images use `object-fit: cover` through the optional `Product.imageUrl` field, with labeled visual placeholders until catalog imagery is connected.
- Menu cards add to a local-only bill preview with quantity controls, clear, subtotal, illustrative 8% tax, and total. No sale or payment is persisted. The supplied background contains its original iStock watermark.
- Lower charts, inventory health, recommendations, anomalies, and activity remain dashboard content; they are arranged in their own chapters rather than crammed into one long opening view.
- The centered video uses the existing optimized local clip, plays only near the viewport, pauses offscreen, and becomes a static poster under reduced motion. When this slide becomes active, all four pastel geometric forms fall together, straighten upright, and remain fixed after landing. Reduced-motion mode shows the upright final positions without the fall animation.
- Subsequent dashboard story chapters use the provided architectural and restaurant photography as full-slide backgrounds, with dark overlays behind white chapter headings and the original readable data cards layered above. The overview, financial performance, revenue, inventory/demand, and recommendations chapters each have a distinct image.
- Revenue performance uses the latest supplied wine-and-table photo. Its chart window is intentionally shorter and narrower, and the background is bottom-aligned so both wine glasses remain unobstructed; on narrow screens the full image is scaled to width to preserve both glasses.
- Horizontal overflow is clipped at the document boundary; the dashboard chapter links and data tables retain their own intended horizontal scrolling.

