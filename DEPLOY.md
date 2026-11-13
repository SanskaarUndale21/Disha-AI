# Disha AI: run and deploy

## One command
```
powershell -ExecutionPolicy Bypass -File start_all.ps1
```
Starts the API (8000), admin panel (5173), citizen portal (5174) and feed panel (5175) and restarts any that crash.
`stop_all.ps1` stops them. Logs are in `logs/`.

## First time
1. Python 3.12 venv in `.venv` with `backend/requirements.txt` installed; model weights in `models/` (not in git).
2. Copy `backend/.env.example` to `backend/.env` and fill it in.
3. `cd frontend && npm install && npx vite build`.

## Panels
| Panel | Who | Address |
|---|---|---|
| Admin panel | Officers and admins (sign in required) | http://localhost:5173 |
| Citizen portal | Public | http://localhost:5174 |
| Feed panel | Operators feeding video, photos, live camera or an IP stream | http://localhost:5175 |
| Map and route planner | Public, officers get repair actions | http://localhost:8000/map |

## Testing
- `python tests/stress.py` : load, websocket fan-out, concurrent analysis, alarm, fuzzing.
- `python tests/auth_sweep.py` : lists every API call that works without sign-in.

## Honest limits
- Person-down detection is a body-shape rule on a pose model. It is not a crash detector and has only been tested on staged footage.
- Depth and width from one photo is an estimate.
- Road ownership records are sample data until replaced with the authority's register.
- The emergency "notify" step is a placeholder; no real call or SMS is sent.
- Put the API behind HTTPS (a reverse proxy or a tunnel) before exposing it to the internet.

## Hosted frontends (Vercel)
- Citizen website: https://disha-ai-citizen.vercel.app (folder `citizen_web`, API address in `citizen_web/config.js`)
- Admin panel: https://disha-ai-admin.vercel.app (folder `frontend`, built with `VITE_API_BASE`, rewrite rules in `frontend/public/vercel.json`)
- Redeploy: `cd citizen_web && vercel deploy --prod --yes`; admin: `cd frontend && VITE_API_BASE=<api> npx vite build && vercel deploy dist --prod --yes`
- The backend is not on Vercel. When the Cloudflare tunnel address changes, update `config.js`, `frontend/public/vercel.json`, rebuild and redeploy both.
