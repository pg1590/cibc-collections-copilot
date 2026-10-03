# Collections Copilot — frontend

Local web UI for Collections Copilot (team Adda Wale). Next.js 15 (App Router), React 19, TypeScript, Tailwind CSS v4, shadcn/ui components (in `src/components/ui`), and lucide icons. It talks only to the local FastAPI backend described in `../docs/api-contract.md`. It shows no built-in sample data: every number and record comes from the API.

## Requirements

- Node.js 20.9 or newer (tested target: Node 22.2)
- The backend running on `http://127.0.0.1:8000` and serving the contract under `/api`

## Setup

```bash
cd frontend
npm install        # creates package-lock.json on first run
npm run dev        # http://127.0.0.1:3000
```

The dev server forwards every `/api/...` request to `http://127.0.0.1:8000/api/...`. If the backend runs somewhere else, set `BACKEND_URL` (for example `BACKEND_URL=http://127.0.0.1:9000 npm run dev`).

Other scripts:

| Command | What it does |
| --- | --- |
| `npm run build` | Production build (also type-checks) |
| `npm start` | Serve the production build on 127.0.0.1:3000 |
| `npm run typecheck` | TypeScript check only |
| `npm run lint` | ESLint with the Next.js rules |

## Signing in

The login page offers the three local demo accounts: `analyst`, `agent` and `supervisor`. Passwords are set by the backend's local environment; the root README lists the local defaults. The browser keeps the token in `sessionStorage`, so closing the tab signs you out. **Sign out** clears it straight away.

The UI hides sections a role cannot use, but that is only for convenience. The backend checks every request.

| Section | Analyst | Agent | Supervisor |
| --- | --- | --- | --- |
| Overview | ✓ | ✓ | ✓ |
| Customers (agents see assigned cases only) | ✓ | ✓ | ✓ |
| Ask Collections | ✓ | | ✓ |
| Agent brief | | ✓ | ✓ |
| Supervisor review (decisions and audit log: supervisor only) | | view | ✓ |
| Data quality and feature registry | ✓ | | ✓ |

## Layout

```
src/app/login            sign-in page
src/app/(app)/overview   pipeline state and actual counts
src/app/(app)/customers  search, list, and customer detail ([id])
src/app/(app)/ask        questions, answer, SQL/sources, refusals
src/app/(app)/briefs     generate a brief for one customer
src/app/(app)/reviews    approve / edit / reject with a reason; audit log
src/app/(app)/quality    data-quality checks and feature registry/parity
src/lib                  API client, session, types, helpers
src/components           app shell, shared states, shadcn/ui components
```
