# Morrow frontend

Next.js App Router + React + TypeScript UI for the business command center.

## Run locally

Use Node.js 20 or later:

```sh
npm install
npm run dev
```

The default `NEXT_PUBLIC_DATA_MODE=mock` uses isolated sample records for visual development. The application labels sample content and preview actions; authentication and business writes do not claim to persist in this mode. To connect the API, set `NEXT_PUBLIC_DATA_MODE=http` and `NEXT_PUBLIC_API_URL` in a local `.env.local`. The backend API must be running and an account must be registered before signing in.

The UI keeps access tokens in memory for this prototype. Production deployment should use a server-side session or an httpOnly-cookie BFF. Payment processing, password reset delivery, invitations, exports, and general record editing require integrations that are not configured; unavailable controls are disabled or return explicit API errors.

## Quality checks

```sh
npm run lint
npm run build
npx playwright install chromium
npm run test:e2e
```

The Playwright suite checks every primary navigation destination, keyboard command-palette navigation, mobile navigation, the POS receipt preview, preview-mode authentication behavior, and password-reset messaging. It does not replace backend transaction integration tests.

## Routes

The frontend has dedicated dashboard, POS, sales, inventory, suppliers, analytics, notifications, recommendations, invoice capture, business assistant, voice assistant, and authentication screens. The remaining workspace sections use the shared, clearly labeled visual-preview layout. See `DESIGN_SYSTEM.md` for the video reference analysis, component system, and styling conventions.
