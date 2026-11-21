# Game Theory — Claude Code prompts (paste one phase at a time)

## 0. One-time setup (you, in PowerShell)

```powershell
# Prerequisites: Git, Python 3.12+, uv, Node LTS, Docker Desktop (optional), Ollama for Windows (optional)

# Make sure Claude Code bills your subscription, not an API key:
echo $env:ANTHROPIC_API_KEY        # must print nothing. If it prints a key: Remove-Item Env:ANTHROPIC_API_KEY
                                   # and delete it from System Environment Variables.

mkdir F:\Projects\GameTheory\docs
cd F:\Projects\GameTheory
# copy CLAUDE.md   -> F:\Projects\GameTheory\CLAUDE.md
# copy SPEC.md     -> F:\Projects\GameTheory\docs\SPEC.md
# copy PROMPTS.md  -> F:\Projects\GameTheory\docs\PROMPTS.md
git init
git add . ; git commit -m "docs: spec and claude instructions"
```

Open the folder in PyCharm → Terminal → run `claude`. Inside Claude Code run `/status` once to confirm it's on your subscription.

**Usage-saving routine for every phase:** paste the phase prompt → let it finish → test in the browser → `git commit` → `/clear` → next phase. Optional: press Shift+Tab for plan mode on Phases 1, 4 and 5 so you approve the plan before code is written.

## Phase 1 — Scaffold & architecture skeleton

Read CLAUDE.md and docs/SPEC.md sections 2, 8, 12, 13, 14.

Build the monorepo scaffold for Game Theory at the repo root:

BACKEND (backend/):
- uv project, Python 3.12, deps from CLAUDE.md + dev deps (pytest, pytest-asyncio, respx, hypothesis, ruff, mypy, import-linter).
- app/main.py app factory + Container (constructor DI), core/settings.py (pydantic-settings, .env), core/logging.py (structlog).
- Packages with clear interfaces and docstrings (placeholders are fine where logic comes later):
  api/ (routers: health, sim, world, agents, tribes, metrics, events, snapshots, llm, god; ws hub),
  services/ (SimulationService, SnapshotService, MetricsService),
  sim/ (engine, world, entities, systems, events, rng, clock, spatial_hash),
  ai/ (perception, memory, brains, skills, gametheory, llm),
  persistence/ (SQLModel models + repository), tools/ (bench).
- GET /api/health and GET /api/sim/state working; WS /ws/world sends `hello` + a fake `frame` every 100 ms.
- import-linter contracts enforcing the layering table in SPEC §2.1.
- config/default.yaml, payoffs.yaml, presets/ (empty files with schema comments).
- Tests: health endpoint, settings load, WS hello.

FRONTEND (frontend/):
- Vite + React + TS strict, Tailwind, zustand, R3F + drei + postprocessing, uPlot, vitest, Playwright, ESLint + Prettier.
- Folder structure from SPEC §9.1. Vite proxy /api and /ws → http://localhost:8000.
- api/ws.ts with auto-reconnect + exponential backoff; api/rest.ts; `npm run gen:api` script using openapi-typescript.
- A placeholder scene: smooth rounded pastel island (noise-displaced plane, smooth normals), water plane, soft sun + hemisphere light, OrbitControls, a few bean-shaped agents moving from the fake WS frames.
- TopBar showing connection status + tick.

INFRA:
- docker-compose.yml per SPEC §14 (backend, frontend, ollama under profile "llm"), multi-stage Dockerfiles (dev + prod targets), .env.example, .gitignore, .editorconfig, .dockerignore.
- .run/ PyCharm shared run configurations: "Backend (uvicorn)", "Frontend (vite)", "Backend tests", "Compose up".
- scripts/dev.ps1 that starts backend and frontend in separate windows.
- README.md quickstart (Docker and non-Docker), docs/adr/0001-architecture.md.

Verify: uv run pytest, ruff, mypy, lint-imports, npm run typecheck, npm run build, docker compose config. Do not run the dev servers in the foreground.
Finish with a summary and the exact commands for me to run. Stop.

## Phase 2 — Simulation core (survival + utility AI)

Read CLAUDE.md and docs/SPEC.md sections 2.2, 3, 4, 7.1, 7.3, 7.4, 8.

Implement the simulation core in backend/:
- Seeded world generation: OpenSimplex heightmap with radial island falloff, biomes, lakes; GET /api/world/terrain returns heightmap (base64 Float32) + biome map.
- Resources (berries, trees, water, rabbits, deer) with regrowth; day/night and seasons; scarcity multiplier.
- Agents with needs, traits, inventory, lifecycle (aging, death causes), spawn from WorldConfig.
- Spatial hash for neighbor queries.
- Perception (radius-limited observation), basic episodic memory.
- Skill base class + SkillRegistry with auto-discovery; survival skills: Wander, MoveTo, Gather, Eat, Drink, Sleep, HuntRabbit, Flee.
- Utility AI brain: considerations + response curves + softmax temperature; store a decision trace (top 3 options with scores) per agent.
- Engine in a worker thread: fixed dt, speed presets 0/1/2/5/10/25/50/MAX, pause, step(n), reset(seed, config). Commands via queue.
- SimulationService wiring; REST control endpoints from SPEC §8; WS broadcasts real `frame` (≤20 Hz, compact arrays) and batched `events`.
- app/tools/bench.py: headless run, prints ticks/sec for --agents and --ticks.

Tests: determinism (same seed ⇒ identical state after 1000 ticks), needs decay, each skill's preconditions/effects, speed/pause/step/reset behaviour, spatial hash correctness vs brute force (hypothesis).
Run the bench with 100, 500, 1000 agents and report the numbers. Stop.

## Phase 3 — 3D world, camera & controls

Read CLAUDE.md and docs/SPEC.md sections 9 and 8 (WS part).

Implement the frontend world:
- Terrain mesh from /api/world/terrain (smooth normals, vertex colors per biome, soft pastel palette), animated water shader, light fog.
- Instanced vegetation and resources (round trees, berry bushes that visibly empty/refill, smooth rocks), instanced animals.
- Agents as InstancedMesh bean characters: tribe colour, size by age, dot eyes, squash-and-stretch walk bob, emoji state sprite above head. Interpolate between WS frames.
- Day/night lighting cycle synced to sim time; campfire glow placeholder.
- CameraRig: zoom (clamped), orbit, pan, WASD/arrows, Q/E rotate, follow selected agent (F/Esc), double-click focus with smooth fly-to.
- ControlBar: play/pause, speed presets 1×…MAX, step, reset (confirm dialog with seed field). Keyboard shortcuts from SPEC §9.3. Help overlay on "?".
- Hover tooltip; click → Inspector panel (needs bars, traits radar, current skill, decision trace). Subscribe/unsubscribe agent detail over WS.
- Quality setting (low/med/high: shadows, postprocessing, pixel ratio), FPS counter.
- Playwright smoke tests: page loads, canvas renders, pause/play changes /api/sim/state, speed preset applies, reset returns tick to 0.

Target 60 FPS at 500 agents on "med". Stop and tell me what to check in the browser.

## Phase 4 — Game theory, manipulation & tribes

Read CLAUDE.md and docs/SPEC.md sections 5, 6, 7.2, 7.3, 10.

Backend:
- EncounterResolver + games: Prisoner's Dilemma (iterated, per-pair history), Stag Hunt (deer needs ≥2 hunters), Hawk–Dove, Ultimatum (trades), Public Goods (tribe storage each season). Payoffs from config/payoffs.yaml; trembling-hand noise.
- All strategies from SPEC §5.2 (LLM strategy can be a stub that falls back to TitForTat for now).
- Social memory: per-pair trust + history; reputation beliefs; gossip (truthful and false) with trust-weighted updates; lie detection.
- Social / manipulation / combat / tribe skills from SPEC §7.3.
- Tribes: emergence via community detection on the trust graph + FoundTribe skill, leader legitimacy, storage, camp, territory, coups, splits, wars, peace.
- Reproduction with trait blending + strategy mutation.
- MetricsService computing SPEC §10 metrics every N ticks; GET /api/metrics; WS `metrics`.
- Tournament preset (SPEC §5.3).

Frontend:
- Charts panel (uPlot): population by tribe, strategy shares over time, cooperation rate per game, avg payoff per strategy, food Gini.
- Event feed with filters; clicking an event flies the camera there.
- Overlays: trust lines (green ally / red enemy, thickness = |trust|), tribe territory rings, camps with dome huts.
- Inspector: relationships list, recent memories, strategy, tribe role.

Tests: each strategy's move table, payoff correctness, TFT vs AlwaysDefect over 10 rounds, Grudger never forgives, gossip update math, tribe formation on a hand-built trust graph, determinism still green.
Stop and suggest 3 presets/experiments for me to try.

## Phase 5 — LLM minds (local Ollama, free, rate-limited)

Read CLAUDE.md and docs/SPEC.md sections 7 (all), 8 (llm endpoints), 12.

Implement the deliberative layer:
- ai/llm: LLMProvider protocol, OllamaProvider (httpx → /api/chat, `format` = JSON schema from pydantic, disable thinking mode when the model supports it, configurable model), MockProvider (deterministic plans built from the agent's state — default and automatic fallback).
- LLMScheduler: queue, max concurrency, calls/min, per-agent min interval, timeout, LRU cache, circuit breaker, high-speed policy (off/reduced), all configurable at runtime.
- PromptBuilder with jinja2 templates (persona, situation, top-K memories, relationships, available skills filtered by check(), output schema). Keep prompts < 1500 tokens; log token estimates.
- Intention integration: plan biases utility scores until done/expired/invalid; stale results discarded; one repair retry on invalid JSON.
- Reflections for LLM agents every N important events.
- Choose LLM agents per WorldConfig (llm_agents count); they get a glowing halo.
- WS `speech` messages → speech bubbles above heads; Inspector shows LLM thought, goal, plan, last prompt/response.
- LLM monitor panel + settings (enable, provider, model, limits). Banner when Ollama is unreachable or circuit is open.
- GET /api/llm/status, /api/llm/stats, PUT /api/llm/settings.

The whole app must work with Ollama not installed. Tests with MockProvider and respx-faked Ollama (success, timeout, invalid JSON, 500s → circuit breaker).
Do NOT install Ollama or pull models. At the end print the PowerShell commands I need (install link, `ollama pull qwen3:8b` and a smaller alternative, how to verify with `ollama list`, and the .env lines to switch LLM_PROVIDER=ollama). Stop.

## Phase 6 — God tools, presets, snapshots, polish

Read CLAUDE.md and docs/SPEC.md sections 9.4, 11, 12.

- New World dialog with presets (Peaceful Eden, Harsh Winter, Liars' Island, Tribal Wars, Axelrod Tournament, LLM Schemers) + sliders for WorldConfig.
- God tools: drop food, drought, plague, spawn agent with chosen strategy/brain, smite. POST /api/god/{action}.
- Snapshots: save/list/load via SQLite (gzipped JSON), UI buttons.
- Minimap with agent dots + camera frustum, screenshot button, legend.
- Performance pass: profile the backend at 500 agents (report hotspots), frontend 60 FPS check, fix the top issues.
- README: architecture diagram (mermaid), controls table, presets, capacity table from SPEC §7.6 with my real bench numbers, troubleshooting.
Stop.

## Phase 7 — Senior review & hardening (optional)

Act as a senior reviewer for this repo. Run every linter, type check and test suite. Check the CLAUDE.md architecture rules (layering, determinism, no cloud AI, file size, DI). Find dead code, missing tests, flaky tests and UX bugs. Fix what's safe; list the rest in docs/REVIEW.md with priority. Stop.

## Reusable templates

### Bug fix

```
Bug: <what happens>
Expected: <what should happen>
Steps: <how to reproduce>
Find the root cause, fix it with the smallest change, add a regression test, run only the related tests. Explain the cause in 2 lines.
```

### New feature

```
Feature: <description>
Read CLAUDE.md and the SPEC sections it touches. Propose the design in ≤10 bullets (files, classes, API changes), wait for my OK, then implement with tests and update SPEC.md.
```

### New skill (agent action)

```
Add skill <Name>(<params>) in category <category>: <what it does, preconditions, effects, utility idea>. Register it, expose it to the LLM schema, add unit tests, add its emoji/animation in the frontend.
```
