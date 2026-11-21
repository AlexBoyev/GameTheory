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
- Architecture decisions: [`docs/adr/`](docs/adr/) - [0001 architecture](docs/adr/0001-architecture.md),
  [0002 simulation core](docs/adr/0002-simulation-core.md),
  [0003 game theory and tribes](docs/adr/0003-game-theory-and-tribes.md)
- Working rules for Claude Code: [`CLAUDE.md`](CLAUDE.md)

---

## Status: Phase 4 of 7 (game theory, manipulation and tribes)

What works right now:

| Works | Not yet |
| --- | --- |
| **A real simulation**: seeded island, resources with regrowth, day/night, seasons | LLM minds and speech bubbles with real dialogue (Phase 5) |
| Agents with needs, traits, inventory, ageing and named death causes | Snapshots you can reload, god tools, presets with real values (Phase 6) |
| **31 skills**: survival, building, social, manipulation, combat and tribe actions | Minimap, tournament report, polish pass (Phase 6-7) |
| Utility AI with response curves, softmax personality and a top-3 decision trace | |
| **Five games**: Prisoner's Dilemma, Stag Hunt, Hawk-Dove, Ultimatum, Public Goods | |
| **Ten strategies** from AlwaysCooperate to Detective, inherited with mutation | |
| **Trust you earn and reputation you only hear about**, gossip, lies, lie detection | |
| **Tribes** that are founded and joined, with leaders, storage, territory, coups, wars and peace | |
| Shelters that get built, reproduction with trait blending, deaths with causes | |
| Engine on a worker thread: pause / play / 1x-50x / MAX / step / reset | |
| Full UI: inspector, event feed with filters, charts, overlays, URL state, help | |
| 7 layering contracts, **202 backend tests**, 21 frontend tests | |

`GET /api/sim/state` reports `"placeholder": false`. Determinism is
machine-checked: same seed, same world, to the bit, after 1,000 ticks of the
full pipeline, with the LLM off.

### What a world actually does

From a 25x run on the default seed (1337), around tick 10,000 - read from
`/api/metrics` and `/api/tribes`, not from the design document:

| | |
| --- | --- |
| Population | 120 spawned -> 140 alive (births outpacing deaths) |
| Tribes | 16, named, each with a leader, a store and territory |
| Shelters built | 69 |
| Cooperation rate | 70% in the Prisoner's Dilemma, 77% Hawk-Dove, 100% Stag Hunt |
| Food Gini | 0.79 - the island has developed a rich and a poor |
| Gifts / betrayals | 717 / 77 |
| Lies told / caught | 878 / 301 |
| Wars declared | 9, with alliances, peace deals and 10 attempted coups |

### Measured on this machine

`python driver.py --bench` (pure engine, no server, no pacing). These numbers
are for the **full Phase 4 pipeline** - encounters, gossip and tribes included,
which is roughly twice the per-tick work of Phase 2:

| Agents | Ticks/sec | vs realtime (1x = 10 ticks/s) | Phase 2 was |
| --- | --- | --- | --- |
| 100 | 341 | 34x | 618 |
| 500 | 42 | 4.2x | 85 |
| 1000 | 17 | 1.7x | 37 |

The default world of 120 agents therefore runs comfortably at any preset up to
25x. At 500 agents the sustainable preset is 5x; at 1,000 it is 1x. Presets
above the sustainable rate are not an error - the engine runs as fast as the
CPU allows and `ticks_per_second` in `/api/sim/state` tells you what you are
really getting. World build is 0.4 s at every size.

**Survivability is a tested invariant**, not an assumption: 92-99% of the
population survives 6,000-12,000 ticks across seeds, with occasional
starvation as the remaining pressure. See
[`docs/adr/0002-simulation-core.md`](docs/adr/0002-simulation-core.md) for the
two balance bugs that made the first cut of the simulation kill 88% of its
population while every unit test passed, and
[`docs/adr/0003-game-theory-and-tribes.md`](docs/adr/0003-game-theory-and-tribes.md)
for the metrics-sampling and coup-accounting bugs that only a running world
exposed.

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
| `python driver.py --no-reload` | Do not restart the backend when its sources change |
| `python driver.py --install` | Install dependencies and exit |

It needs nothing but the system Python - stdlib only - and Ctrl+C stops both
servers and their children.

### Or by hand

```powershell
# 1. backend
cd backend
uv sync
uv run uvicorn app.main:app --port 8000                # or --port 8001
# Note: --reload hangs on this host (see ADR 0003). `python driver.py`
# watches the sources and restarts the backend itself instead.

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
