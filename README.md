# Game Theory

An autonomous 3D society simulation: agents with needs, personalities and
game-theory strategies live on a soft pastel island. They gather, hunt, share,
steal, lie, gossip, form tribes, elect leaders, ally, betray and go to war -
with no player input. You are the observer: orbit, zoom, follow an agent,
fast-forward, inspect minds, change the rules, reset, and see which strategies
survive.

Runs entirely on `localhost`. **No paid services, no API keys, no cloud AI.**

- Design: [`docs/SPEC.md`](docs/SPEC.md)
- Build plan: [`docs/PROMPTS.md`](docs/PROMPTS.md)
- Architecture decisions: [`docs/adr/0001-architecture.md`](docs/adr/0001-architecture.md)
- Working rules for Claude Code: [`CLAUDE.md`](CLAUDE.md)

---

## Status: Phase 2 of 7 (simulation core)

What works right now:

| Works | Not yet |
| --- | --- |
| **A real simulation**: seeded island, resources with regrowth, day/night, seasons | Game theory, trust, gossip, tribes (Phase 4) |
| Agents with needs, traits, inventory, ageing and named death causes | Social and manipulation skills (Phase 4) |
| 8 survival skills - Wander, MoveTo, Gather, Eat, Drink, Sleep, HuntRabbit, Flee | Reproduction, metrics, charts (Phase 4) |
| Utility AI with response curves, softmax personality and a top-3 decision trace | LLM minds and speech bubbles (Phase 5) |
| Engine on a worker thread: pause / play / 1x-50x / MAX / step / reset | Snapshots, god tools, presets with real values (Phase 6) |
| `GET /api/world/terrain`, `/api/agents`, `/api/agents/{id}`, `/api/events` | Vegetation detail, emoji states, inspector panel (Phase 3) |
| `WS /ws/world`: real frames at 20 Hz with resource deltas and batched events | Tribes, snapshots, god tools (return **501** naming their phase) |
| 3D island from the **backend heightmap**, biome colours, resources you can watch empty | Charts, event feed UI, minimap (Phase 3+) |
| 7 layering contracts, 117 backend tests, 21 frontend tests | |

`GET /api/sim/state` now reports `"placeholder": false`. Determinism is
machine-checked: same seed, same world, to the bit, after 1,000 ticks of the
full pipeline.

### Measured on this machine

`python driver.py --bench` (pure engine, no server, no pacing):

| Agents | Ticks/sec | vs realtime (1x = 10 ticks/s) | World build |
| --- | --- | --- | --- |
| 100 | 618 | 62x | 0.4 s |
| 500 | 85 | 8.4x | 0.5 s |
| 1000 | 37 | 3.7x | 0.5 s |

So 500 agents comfortably sustain the 5x preset and roughly reach 8x; 1000
agents sustain 2x. Speed presets above the sustainable rate simply run as fast
as the CPU allows rather than keeping up.

**Survivability is a tested invariant**, not an assumption: 92-99% of the
population survives 6,000-12,000 ticks across seeds, with occasional
starvation as the remaining pressure. See
[`docs/adr/0002-simulation-core.md`](docs/adr/0002-simulation-core.md) for the
two balance bugs that made the first cut of this phase kill 88% of its
population while every unit test passed.

---

## Before you start: two things about this machine

1. **Port 8000 is taken by Apache** (`httpd`). The backend cannot bind it as
   shipped. Either stop that service, or run the backend on another port -
   everything follows the port automatically:

   ```powershell
   .\scripts\dev.ps1 -BackendPort 8001      # non-Docker
   # or, for Docker:  BACKEND_PORT=8001 in .env
   ```

2. **Node 20.12.1 is below what the toolchain wants.** Vite needs >= 20.19,
   and Vite 8 / vitest 5 need >= 22.14 (their native bindings are skipped on
   Node 20, so vitest cannot start at all). The frontend is therefore pinned to
   Vite 7 + vitest 3, which work here. Node 20 is also past end-of-life.
   **Upgrading to Node 22 LTS is recommended**, after which:

   ```powershell
   cd frontend
   npm install -D vite@latest vitest@latest @vitejs/plugin-react@latest jsdom@latest
   ```

   That also clears the two `npm audit` advisories, which are in vitest 3 and
   are dev-only (the test runner is never shipped).

---

## Quickstart

One command installs what is missing, picks a free port, starts both servers
and opens the browser:

```powershell
python driver.py
```

| Command | What it does |
| --- | --- |
| `python driver.py` | Install if needed, start backend + frontend, open the browser |
| `python driver.py --check` | Every linter, type check and test suite (9 checks) |
| `python driver.py --bench` | Throughput benchmark |
| `python driver.py --port 8001` | Pin the backend port (default: first free from 8000) |
| `python driver.py --no-frontend` | Backend only |
| `python driver.py --install` | Install dependencies and exit |

It needs nothing but the system Python - stdlib only - and Ctrl+C stops both
servers and their children.

### Or by hand

```powershell
# 1. backend
cd backend
uv sync
uv run uvicorn app.main:app --reload --port 8000      # or --port 8001

# 2. frontend (second terminal)
cd frontend
npm install
npm run dev
```

Open <http://localhost:5173>. API docs: <http://localhost:8000/docs>.
`scripts\dev.ps1` does the same in two PowerShell windows.

PyCharm users: the shared run configurations in `.run/` (**Backend
(uvicorn)**, **Frontend (vite)**, **Backend tests**, **Compose up**) appear in
the run-configuration dropdown automatically.

## Quickstart - with Docker

```powershell
copy .env.example .env
docker compose up --build                    # backend :8000, frontend :5173
docker compose --profile llm up --build      # ... plus a containerised Ollama
```

On Windows the simpler LLM setup is **native Ollama** (it gets the GPU without
passthrough); leave the `llm` profile alone and the backend reaches the host
daemon at `host.docker.internal:11434`.

---

## Commands

| Where | Command | What |
| --- | --- | --- |
| `backend/` | `uv run uvicorn app.main:app --reload --port 8000` | Run the API |
| `backend/` | `uv run pytest` | Tests |
| `backend/` | `uv run ruff check . ; uv run ruff format .` | Lint and format |
| `backend/` | `uv run mypy app` | Type check (strict) |
| `backend/` | `uv run lint-imports` | **Layering contracts** |
| root | `python driver.py` | Run the whole stack |
| root | `python driver.py --check` | All 9 checks |
| `backend/` | `uv run python -m app.tools.bench --agents 500 --ticks 2000` | Throughput |
| `backend/` | `uv run python -m app.tools.dump_openapi` | Schema without a server |
| `frontend/` | `npm run dev` | Vite dev server |
| `frontend/` | `npm run build` / `npm run typecheck` / `npm run lint` | Build and checks |
| `frontend/` | `npm run test` | Unit tests (vitest) |
| `frontend/` | `npm run e2e` | Playwright smoke (needs `npm run e2e:install` once) |
| `frontend/` | `npm run gen:api` | Regenerate REST types from a running backend |
| `frontend/` | `npm run gen:api:offline` | ... from a dumped `openapi.json` |
| root | `docker compose up --build` | Whole stack |

## Layout

```
GameTheory/
  driver.py  CLAUDE.md  README.md  docker-compose.yml  .env.example  .run/
  docs/      SPEC.md  PROMPTS.md  adr/
  backend/   pyproject.toml  Dockerfile  config/
             app/
               main.py        app factory
               container.py   the one composition root
               core/          settings, logging, Result, WorldConfig
               api/           routers, DTOs, WS hub        (transport only)
               services/      simulation, engine factory, world queries, metrics
               sim/           PURE deterministic engine
                 balance.py   every tuning dial, in one file
                 engine.py    worker thread, command queue, frame output
                 worldgen/    terrain, resources, population
                 systems/     needs, movement, regrowth, lifecycle
               ai/            perception, minds, brains, skills, game theory, llm
                 skills/      the 8 survival skills + registry
                 systems/     perception, decision, skill execution
               persistence/   SQLModel + repository
               tools/         bench, openapi dump
             tests/{sim,ai,api}/
  frontend/  package.json  Dockerfile  nginx.conf  vite.config.ts
             src/{app,api,state,scene,ui,lib}  tests/  e2e/
  data/      (gitignored - SQLite and snapshots)
```

## How the layering is enforced

`uv run lint-imports` checks seven contracts, so the architecture fails CI
rather than review. The strongest one is determinism: **`sim/` may not import
`time`, `datetime`, `random`, `secrets` or `uuid`.** The engine gets a seeded
`numpy.random.Generator` per named substream and an injected `Pacer` for wall
time. See ADR 0001 for the one place we deliberately tightened SPEC 2.1.

## Troubleshooting

| Symptom | Cause and fix |
| --- | --- |
| `error while attempting to bind on address ('127.0.0.1', 8000)` | Something else owns the port - here, Apache. Use `-BackendPort 8001`. |
| Frontend shows "Connecting to the simulation..." forever | Backend is not running, or is on a different port than the Vite proxy. Set `VITE_BACKEND_URL` or use `scripts/dev.ps1`. |
| `vitest` fails with "Cannot find native binding" | Node is below the version its bindings require. Use Node 22 LTS, or the pinned Vite 7 / vitest 3. |
| An endpoint returns **501** | Intentional: the response body names the phase it lands in. |
| `llm.reachable: false` in `/api/health` | Expected without Ollama. The app falls back to deterministic mock plans and keeps working. |
| Playwright: "browser not installed" | `npm run e2e:install` (downloads Chromium once). |
| Agents float above or sink into the island | Terrain and agents must share one sampler. Both read the backend heightmap via `src/api/terrain.ts`; the noise island in `src/lib/terrain.ts` is only the fallback for when `/api/world/terrain` is unreachable. |
| Everyone dies within a few sim-days | A balance regression. Run `uv run pytest tests/sim/test_balance.py` - it reports the death causes. |

## Cost and safety

No cloud AI, no API keys, no billing - by design and by rule (`CLAUDE.md`). The
only outbound network call the backend can make is to Ollama on the configured
local URL. `MockProvider` is the default, so the whole application works with
nothing installed.
