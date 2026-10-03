# Frontend implementation notes (Claude Opus 5.5)

Date: 3 October 2026. Scope: `frontend/**` only, built against `docs/api-contract.md` (API v1). No backend files were touched. No subagents, commits, deployment or paid APIs.

## What was built

- Next.js 15.5 App Router, React 19.1, TypeScript strict, Tailwind v4, shadcn/ui (new-york) components written by hand into `src/components/ui` (button, input, textarea, label, card, badge, table, alert, skeleton, collapsible, separator, tabs) on Radix primitives, plus lucide icons.
- `/api/:path*` is rewritten to `${BACKEND_URL:-http://127.0.0.1:8000}/api/:path*` in `next.config.ts`.
- API client (`src/lib/api.ts`): bearer token from `sessionStorage`; FastAPI `detail` shown as text, including validation lists; a 401 clears the session and returns to sign-in; clear messages for 403/502/503/504 and network failure.
- Sections: Overview (`/health` + `/overview`), Customers list/detail, Ask Collections (`/ask`, expandable SQL/sources, refusal panel, result rows), Agent brief (`/briefs`: summary, signals/evidence, recommendation, policy sources, draft, model name/version, features, pending-review notice), Supervisor review (`/reviews`, `POST /reviews/{id}` approve/edit/reject; reason required, edit requires a changed draft; `/audit` for supervisors), Data quality and Feature registry (`/quality`, `/features` parity).
- Every view has loading, error (with retry) and empty states. Contract fields that are open-ended (accounts, cases, identity, notes, definitions, rows, audit) are rendered column-by-column from what the backend actually returns. Nothing is invented.
- Accessibility: semantic headings and landmarks, skip link, labelled form controls, radio groups in fieldsets, keyboard-reachable Radix tabs/collapsibles, `aria-live` for results, visible focus rings. Responsive layout with an off-canvas sidebar below `lg`.

## Verification status: NOT VERIFIED

`npm` was blocked by the session's permission policy: even `npm -v` was auto-denied. So:

- `npm install` was not run; **no `package-lock.json` exists yet**.
- `npm run build`, `npm run typecheck` and `npm run lint` were **not run**. The code was written carefully against the listed library APIs, but it has not been compiled.
- Package versions were chosen from known releases up to the model's knowledge, not checked against the npm registry or current Next.js docs (no web access). Next 15.5 was picked over 16 to avoid the 16.x breaking changes. Both support Node 22.2 (Next 15 needs ≥18.18; 16 needs ≥20.9).
- No end-to-end run against the backend, which did not exist yet (`app/` was empty).

Required follow-up (supervisor or Codex): `cd frontend && npm install && npm run typecheck && npm run lint && npm run build`, then commit the generated `package-lock.json` and fix any reported errors.

## Assumptions to confirm with the backend owner

1. The backend mounts routes under `/api` (the proxy keeps the prefix). If it serves them at the root, change the rewrite destination to `${backend}/:path*`.
2. Demo usernames are `analyst`, `agent` and `supervisor`; the login form pre-fills these, and the user can still type any username. Passwords are never stored in the frontend.
3. A review counts as pending when `status === "pending"` and `decision` is empty.
4. `POST /reviews/{id}` returns the updated `ReviewItem`, which replaces the card in place.
5. UI role visibility: Ask is analyst/supervisor; Brief is agent/supervisor; Reviews are visible to agent (read-only) and supervisor; Quality/Features are analyst/supervisor. The backend is the authority.
6. `identity_confidence` is shown as a raw value, and the UI says it is a match score, not a calibrated probability.

## Codex verification

Dependencies updated to Next.js 15.5.27 and React 19.3.0, with a committed package lock. TypeScript, ESLint and the production build all passed on Node 22.2.0. The initial npm install emitted an engine warning from an ESLint transitive package, but all required frontend checks completed. Browser/backend integration is being checked separately. Initial Claude source ownership has ended; subsequent fixes are owned by Codex.
