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
  [0003 game theory and tribes](docs/adr/0003-game-theory-and-tribes.md),
  [0004 LLM minds](docs/adr/0004-llm-minds.md)
- Working rules for Claude Code: [`CLAUDE.md`](CLAUDE.md)

---

## Status: Phase 5 of 7 (LLM minds)

What works right now:

| Works | Not yet |
| --- | --- |
| **A real simulation**: seeded island, resources with regrowth, day/night, seasons | Snapshots you can reload, god tools, presets with real values (Phase 6) |
| Agents with needs, traits, inventory, ageing and named death causes | New World dialog, minimap, screenshot, heatmap, name tags (Phase 6) |
| **31 skills**: survival, building, social, manipulation, combat and tribe actions | Tournament report, senior review pass (Phase 6-7) |
| Utility AI with response curves, softmax personality and a top-3 decision trace | |
| **Deliberative minds**: goals, plans, spoken lines and beliefs, via local Ollama **or an offline mock** | |
| LLM monitor: provider, reachability, call log with real prompts and replies | |
| **Five games**: Prisoner's Dilemma, Stag Hunt, Hawk-Dove, Ultimatum, Public Goods | |
| **Ten strategies** from AlwaysCooperate to Detective, inherited with mutation | |
| **Trust you earn and reputation you only hear about**, gossip, lies, lie detection | |
| **Tribes** that are founded and joined, with leaders, storage, territory, coups, wars and peace | |
| Shelters that get built, reproduction with trait blending, deaths with causes | |
| Engine on a worker thread: pause / play / 1x-50x / MAX / step / reset | |
| Full UI: inspector, event feed with filters, charts, overlays, speech bubbles, URL state, help | |
| 7 layering contracts, **276 backend tests**, 31 frontend tests | |

`GET /api/sim/state` reports `"placeholder": false`. Determinism is
machine-checked: same seed, same world, to the bit, after 1,000 ticks of the
full pipeline, with the LLM off. (With it on, replies arrive on the event loop
and no seed controls that timing - set `llm_agents: 0` for a reproducible run.)

**No model is required.** The default provider is an in-process mock that
builds a deterministic plan from the prompt, so goals, speech bubbles and the
monitor all work with nothing installed. See
[Using a real model](#using-a-real-model-optional) to point it at Ollama.

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

| Agents | Ticks/sec | vs realtime (1x = 10 ticks/s) | Phase 4 was |
| --- | --- | --- | --- |
| 100 | 283 | 28x | 341 |
| 500 | 50 | 5.0x | 42 |
| 1000 | 22 | 2.2x | 17 |

500 and 1,000 agents got *faster* than Phase 4 despite the deliberative layer
being added, because a property test found a real bug in the spatial hash on
the way (see below) and fixing it also made the hot path cheaper. The 100-agent
case is slower because four deliberative agents are 4% of a small world and
0.4% of a large one.

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
population while every unit test passed,
[`docs/adr/0003-game-theory-and-tribes.md`](docs/adr/0003-game-theory-and-tribes.md)
for the metrics-sampling and coup-accounting bugs that only a running world
exposed, and [`docs/adr/0004-llm-minds.md`](docs/adr/0004-llm-minds.md) for a
runtime setting that was tested, documented, settable from the API - and wired
to nothing at all.

The neighbour search had a real correctness bug until Phase 5: it scanned a
span of cells around the query's *cell*, when the query point can sit anywhere
inside that cell, so an agent standing within a whisker of a cell border could
not see a neighbour at the edge of its vision. Hypothesis found it; the fix
(derive the cell range from the circle's bounding box) is both correct and
about 20% faster at 500+ agents, because the exact box is often 2x2 cells
where a span was always at least 3x3.

---

## Using a real model (optional)

Everything above works with no model installed - the default provider is an
in-process mock. To let a few agents think with a real local model instead:

```powershell
# 1. Install Ollama for Windows (I will not install it for you):
#    https://ollama.com/download
#    Then, in a new terminal:

ollama pull qwen3:8b            # ~5 GB, good instruction following
# or, on a smaller machine:
ollama pull qwen3:4b            # ~2.5 GB
# or smaller still:
ollama pull llama3.2:3b         # ~2 GB

ollama list                     # confirm it is there
curl http://localhost:11434/api/tags   # confirm the daemon answers
```

Then either switch provider at runtime in the **LLM minds** panel (`m`), or
set it before starting in `.env`:

```ini
LLM_PROVIDER=ollama
OLLAMA_MODEL=qwen3:8b
OLLAMA_URL=http://localhost:11434
LLM_MAX_CONCURRENCY=1
LLM_MAX_CALLS_PER_MIN=30
LLM_HIGH_SPEED_POLICY=reduced
```

How many agents deliberate is a world setting, not a process one -
`llm_agents` in `backend/config/default.yaml` (4 by default, up to 64). Raise
it and lower `LLM_MIN_INTERVAL_SIM_S` for a noisier island; a local 8B model
on one GPU will comfortably keep a handful of agents thinking.

Nothing here reaches the public internet, and there is no API key anywhere in
the project. If the daemon is not running you get a banner saying so, agents
carry on with utility AI, and the circuit breaker stops the retry storm.

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

Keyboard: `m` opens the LLM minds monitor, `c` the charts, `l` the event log,
`b` toggles speech bubbles, `?` lists everything.
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
