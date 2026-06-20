# Aegis Route Dashboard

Lightweight wildfire logistics dashboard for the Aegis Route hackathon demo.

## Run locally

```powershell
npm install
npm run dev
```

The dashboard uses a deterministic mock solver unless `VITE_SOLVER_API_URL` is set.

## Connect the solver

1. Copy `.env.example` to `.env.local`.
2. Set `VITE_SOLVER_API_URL` to the solver service base URL.
3. Expose `POST /optimize` from the solver.

The request and response types are defined in `src/types.ts`. The dashboard sends the architecture document's vehicles, target nodes, and dynamic edge modifiers. The response must include at least one route with an SVG path for this prototype.

If the service times out, errors, or returns no routes, the dashboard automatically deploys its safe fallback route so the live demo can continue.

## Commands

```powershell
npm run dev      # development server
npm run build    # type-check and production build
npm run preview  # serve the production build
```
