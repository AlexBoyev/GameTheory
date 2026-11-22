# Game Theory — Design Spec

> Single source of truth for the design. Claude Code: read only the sections a task points to.

---

## 1. Vision

An autonomous 3D society sandbox. Agents with needs, personalities and game-theory strategies live on a
rounded, toy-like island. They gather, hunt, share, steal, lie, gossip, form tribes, elect leaders,
ally, betray and wage war — with no player input. The user is an observer/god: orbit, zoom, follow
agents, fast-forward, inspect minds, change world rules, reset, and watch which strategies survive.

Runs on `localhost`, opened in the browser. Zero paid services.

---

## 2. Architecture overview

```
┌──────────────────────── Browser (http://localhost:5173) ────────────────────────┐
│ React + TypeScript + @react-three/fiber                                          │
│ scene/ (3D)   ui/ (HUD, panels)   state/ (zustand)   api/ (REST + WS clients)    │
└───────────────┬───────────────────────────────────────────┬──────────────────────┘
          REST /api/*  (control, config, queries)      WS /ws/world (frames, events, metrics)
┌───────────────▼───────────────────────────────────────────▼──────────────────────┐
│ FastAPI backend (Python 3.12) — http://localhost:8000                            │
│ api/        transport only: routers, DTOs, WS hub                                │
│ services/   SimulationService (owns engine lifecycle), SnapshotService, Metrics  │
│ sim/        PURE deterministic engine: world, entities, systems, event bus       │
│ ai/         perception, memory, brains, skills, game theory, LLM gateway         │
│ persistence/ SQLite via SQLModel (runs, metrics, snapshots, events)              │
└───────────────────────────────────────────┬──────────────────────────────────────┘
                                             │ async HTTP, rate-limited, optional
                               ┌─────────────▼─────────────┐
                               │ Ollama (local LLM, free)  │  or MockProvider
                               └───────────────────────────┘
```

### 2.1 Layering rules (enforced in review + import-linter)
| Layer | May import | Must NOT import |
|---|---|---|
| `sim/` | stdlib, numpy, `ai/` interfaces (brains, skills) | FastAPI, httpx, persistence, `ai/llm` providers, wall clock |
| `ai/` | `sim/` read models, numpy | FastAPI, persistence |
| `ai/llm/` | httpx, jinja2, pydantic | `sim/` internals (gets DTOs only) |
| `services/` | everything below | `api/` |
| `api/` | `services/`, DTOs | `sim/` internals directly |

- Dependency injection via constructors; a single `Container` built in `app/main.py` (app factory).
- Engine is deterministic for a given seed when LLM is off (MockProvider is deterministic too).
- Engine runs in a dedicated worker thread; communicates with asyncio via thread-safe queues.
  Commands in (start/pause/speed/step/reset), frames/events out.
- Broadcast to clients ≤ 20 Hz regardless of tick rate. Frontend interpolates.

### 2.2 Time model
- Fixed timestep: `dt = 0.1` sim-seconds per tick, base rate 10 ticks/s at 1×.
- Speed presets: `0 (pause), 1, 2, 5, 10, 25, 50, MAX` (MAX = as fast as CPU allows).
- 1 sim-day = 240 sim-seconds (configurable). 1 season = 7 days. 4 seasons/year.

---

## 3. World

- Island terrain: heightmap from seeded OpenSimplex noise × radial falloff (water at edges). Default 256×256 units, grid resolution 128.
- Biomes by height/moisture: beach, meadow, forest, hills, rocky peaks, lakes.
- Backend owns terrain; sends heightmap (Float32 array, base64) once in `hello`/`GET /world/terrain`. Frontend builds a smooth-shaded mesh.
- Spatial index: uniform-grid spatial hash for neighbor queries (cell = interaction radius).

### 3.1 Resources
| Resource | Where | Behavior |
|---|---|---|
| Berry bush | meadow/forest | N berries, regrows over time; no regrowth in winter |
| Tree | forest | wood for shelters; slow regrowth |
| Water | lakes, river tiles | infinite; drink at shore |
| Rabbit | meadow | solo hunt, small food, respawns |
| Deer (big game) | forest/hills | needs ≥ 2 hunters → **Stag Hunt**; big food |
| Stone | rocky areas | for weapons/shelters (later) |

### 3.2 Environment
- Day/night cycle (lighting + agents sleep at night, predators? optional).
- Seasons: winter → no berry regrowth, faster energy drain. Scarcity slider scales all yields.
- Events (god tools or random): drought, storm, plague, bountiful harvest.

---

## 4. Agents

### 4.1 State
| Field | Notes |
|---|---|
| `id`, `name` | generated, deterministic from seed |
| `age`, `life_stage` | child → adult → elder |
| `health` 0–100 | dies at 0 |
| `needs` 0–100 | hunger, thirst, energy, safety, social (decay per tick) |
| `traits` 0–1 | aggression, honesty, loyalty, greed, sociability, cunning, courage, charisma |
| `strategy` | game-theory gene (see §5.2) |
| `brain_type` | `utility` (default) or `llm` |
| `inventory` | food, wood, stone |
| `tribe_id`, `role` | none / member / leader / elder |
| `position`, `heading`, `velocity` | 2D on terrain (y sampled from heightmap) |
| `current_skill`, `intent` | what it's doing + why |
| `thought` | short text shown in UI (from utility trace or LLM) |
| `memory` | see §7.2 |

### 4.2 Lifecycle
- Death: starvation, dehydration, combat, old age, plague. Body leaves food briefly.
- Reproduction: two adults, mutual trust > threshold, enough food, cooldown → child inherits blended traits + one parent's strategy; mutation (rate configurable) can flip strategy or nudge traits.
- Population cap configurable (soft cap via resource pressure, hard cap for performance).

---

## 5. Game theory

### 5.1 Encounters
When two available agents are within interaction radius, the `EncounterResolver` picks a game by context:

| Context | Game | Cooperate / Defect means |
|---|---|---|
| One has surplus food, other is hungry | Prisoner's Dilemma (iterated, per-pair history) | share / hoard or steal |
| Big game nearby, both hungry | Stag Hunt | hunt deer together / chase rabbit alone |
| Both want the same resource | Hawk–Dove | fight / yield |
| Trade proposal | Ultimatum | fair offer, accept / greedy offer, reject |
| Tribe storage, once per season | Public Goods (N-player) | contribute / free-ride |

- Payoff matrices in `backend/config/payoffs.yaml`. PD default: T=5, R=3, P=1, S=0. Payoffs convert into food/health/trust.
- Trembling-hand noise ε (default 0.02): chance an intended action flips.
- Every decision is logged to both agents' memory and the global interaction log (for metrics).

### 5.2 Strategies (the "gene")
| Strategy | Rule |
|---|---|
| AlwaysCooperate | always C |
| AlwaysDefect | always D |
| TitForTat | C first, then copy partner's last move |
| GenerousTFT | TFT but forgives a D with p=0.1 |
| Grudger | C until betrayed once, then D forever |
| Pavlov | win-stay, lose-shift |
| Detective | probe C,D,C,C; exploit if partner never retaliates, else TFT |
| Random | 50/50 |
| Opportunist | trait-driven: defect when greed × (1-honesty) × advantage is high |
| LLM | decided by the agent's LLM mind (LLM agents only) |

Strategy lookup uses the **agent's memory of that partner** — and, if never met, the partner's *reputation* (gossip-based belief).

### 5.3 Tournament mode
Preset that disables survival and runs a classic round-robin iterated PD tournament among all strategies, with replicator dynamics (next generation proportional to score). Visualized as agents in a ring arena.

**As built.** `tournament_mode` swaps the tick pipeline for `Perception + TournamentSystem` — no needs decay, no skills, no lifecycle, no food changing hands, because a tournament measures strategies and hunger would measure something else as well. Pairings are exhaustive and scheduled rather than spatial (24 pairs a tick, 10 iterated rounds each), so no strategy benefits from lucky neighbours. Cohorts start equal. Standings are **score per round**, not per agent, so a strategy is not rewarded for having more members this generation; `GET /api/sim/tournament` reports them and the UI shows a panel only while one is running.

Selection is `exp(4 · (score − best))` rather than plain proportional: scores land between 2.0 and 2.7, a 1.35:1 advantage that drift drowns over twenty generations of a hundred agents. Every strategy keeps a non-zero share, so one bad generation cannot delete a contestant and stop the tournament being a comparison. Changing strategy clears an agent's pair history — otherwise a fresh defector inherits a reputation for cooperating.

On seed 1337 this reproduces Axelrod's result: AlwaysDefect tops generation 1 and is extinct by generation 19, TitForTat finishes first, and mean score climbs from ~2.3 toward the mutual-cooperation payoff of 3.0. There is a test for it.

---

## 6. Social & manipulation layer

| Mechanic | Implementation |
|---|---|
| Trust | per-pair float [-1, 1]; updated by outcomes, gifts, betrayals, gossip |
| Reputation | each agent's *belief* about others' character; spreads via gossip |
| Gossip | when talking, agents share beliefs about third parties; listener updates weighted by trust in speaker |
| Lying | cunning + low-honesty agents may spread false gossip or fake resource locations; detection chance → caught liars lose reputation |
| Deception in games | signal cooperation, then defect |
| Persuasion | charisma vs target's stubbornness → shifts target's trust/goal |
| Bribery | give food to raise trust / buy a vote |
| Alliances | explicit pacts between agents or tribes; betrayal = big trust crash + gossip broadcast |
| Tribes | emerge from trust clusters (community detection over trust graph every N ticks) or a charismatic agent founding one; shared storage; camp; territory ring |
| Leadership | leader = highest legitimacy (reputation × charisma × tenure); followers can challenge → coup |
| Tribe split | low legitimacy or overpopulation → faction leaves with sub-leader |
| Inter-tribe | raids, wars (sum of strength), peace treaties, trade routes |

All of these are **Skills** (§7.3) — the same actions utility agents and LLM agents use.

---

## 7. AI pipeline

### 7.1 Decision loop per agent
```
Perceive ─► Remember ─► Decide ─► Act ─► Learn
   │           │          │        │       │
 spatial    episodic   3 layers  skill   trust, memory,
 query      + social   (below)   runs    reputation
```

| Layer | Runs | Engine | Decides |
|---|---|---|---|
| **Reactive** | every tick, all agents | Utility AI (considerations × response curves) | eat, drink, sleep, flee, gather, wander |
| **Strategic** | on encounters | strategy gene + memory + reputation | cooperate / defect in games |
| **Deliberative** | every N sim-sec or on major events, **LLM agents only** | LLM via gateway → structured plan | goals, alliances, schemes, speeches, betrayals |

- The LLM produces an **Intention** (goal + ≤3 skill calls + public line + private thought). It *biases* utility scores (bonus to planned skills) until done, expired or invalid. Survival urges can still override (a starving schemer eats first).
- **The simulation never waits for the LLM.** Requests are async; results apply when they arrive; stale results (agent dead, target gone) are discarded.

### 7.2 Memory
| Kind | Structure |
|---|---|
| Working | latest observation |
| Episodic | ring buffer of `MemoryEvent(tick, type, actors, summary, importance 1–10)`; retrieval = importance × recency decay × relevance (actor match) |
| Social | per-partner: trust, interaction history (last K moves), known reputation |
| Reflections (LLM only) | every N events, LLM summarizes into beliefs ("Rex steals — avoid him") stored as high-importance memories |

### 7.3 Skills (action library = LLM tool set)
```python
class Skill(ABC):
    name: ClassVar[str]
    description: ClassVar[str]           # also shown to LLM
    category: ClassVar[SkillCategory]    # survival | social | manipulation | combat | tribe
    Params: ClassVar[type[BaseModel]]    # pydantic → JSON schema for LLM
    cooldown: ClassVar[float]
    def check(self, agent, world, params) -> Result[None, str]   # preconditions + reason
    def utility(self, agent, ctx) -> float                        # for utility AI
    def start(self, agent, world, params) -> SkillRun
    def step(self, run, dt) -> SkillStatus                        # RUNNING | DONE | FAILED
```
- `SkillRegistry` auto-discovers skills; exports JSON schema for LLM prompts. LLM may only call registered skills; invalid calls are rejected and logged.

Initial skill set:
- **Survival:** Wander, MoveTo, Gather(resource), Eat, Drink, Sleep, HuntRabbit, JoinHunt(deer), Flee(from), BuildShelter
- **Social:** Talk(target, topic), Share(target, amount), Trade(target, offer), ProposeAlliance(target), Reproduce(partner)
- **Manipulation:** Gossip(target, about, claim, truthful), Lie(target, false_info), Persuade(target, goal), Bribe(target, amount), Betray(target)
- **Combat:** Attack(target), Defend, Raid(tribe)
- **Tribe:** FoundTribe, Recruit(target), JoinTribe(tribe), LeaveTribe, StoreFood, TakeFromStorage, ChallengeLeader, DeclareWar(tribe), OfferPeace(tribe)

### 7.4 Utility AI
- Each skill's `utility()` combines considerations (need level via response curve, distance, trait multiplier, risk, intention bonus).
- Selection: softmax over top options with temperature (config) → personality-driven variety.
- **Decision trace** (top 3 options + scores + chosen + reason) stored per agent for the inspector.

### 7.5 LLM gateway (local only, free)
```
ai/llm/
  provider.py        # LLMProvider protocol: async generate(LLMRequest) -> LLMResponse
  ollama_provider.py # httpx → OLLAMA_URL /api/chat, `format` = JSON schema, `think: false` when supported
  mock_provider.py   # deterministic heuristic plans; DEFAULT when Ollama unreachable
  scheduler.py       # queue, limits, cache, circuit breaker
  prompt_builder.py  # jinja2 templates in ai/llm/prompts/
  schemas.py         # Intention, PlanStep, Reflection (pydantic)
  telemetry.py       # call log, stats
```
**Hard rule: no cloud providers, no API keys, no billing.**

Scheduler limits (all in config / UI):
| Setting | Default |
|---|---|
| `LLM_PROVIDER` | `mock` (switch to `ollama`) |
| `LLM_MAX_AGENTS` | 8 |
| `LLM_MAX_CONCURRENCY` | 1 |
| `LLM_MAX_CALLS_PER_MIN` | 30 |
| `LLM_MIN_INTERVAL_SIM_S` per agent | 20 |
| `LLM_TIMEOUT_S` | 20 → fallback to utility brain |
| Circuit breaker | 3 consecutive failures → LLM paused 60 s, UI banner |
| High-speed policy | speed > 5× → `reduced` (interval ×4) / `off` |
| Cache | prompt-hash LRU |

Prompt (target < 1,500 tokens): persona (name, traits, strategy, role) → situation (needs, inventory, season, nearby) → top-K memories → top-5 relationships → available skills (from registry, filtered by `check`) → output schema.

Output schema:
```json
{ "thought": "private reasoning, 1-2 sentences",
  "goal": "short goal",
  "plan": [ { "skill": "Gossip", "params": { "target": 12, "about": 7, "claim": "Rex steals", "truthful": false } } ],
  "say": "public line for speech bubble or null" }
```
Validation: pydantic + registry `check()`; one repair retry with the error message; else fallback.

### 7.6 Capacity guidance (also in README)
| Brain | Cost | Realistic count | Decision rate |
|---|---|---|---|
| Utility + strategy | free, CPU | 200–1,000 (sim); rendering fine to ~2k with instancing | every tick |
| LLM via Ollama on GPU (4–8B model) | free | 5–20 "minds" | each every 20–60 sim-s, ~1–4 s per call |
| LLM via Ollama on CPU only | free, slow | 1–4 | each every ~60 s+ |
Include `app/tools/bench.py` to measure real numbers on the user's machine.

---

## 8. Backend API contract

REST (prefix `/api`, all pydantic DTOs, OpenAPI at `/docs`):
| Method & path | Purpose |
|---|---|
| `GET /health` | liveness + LLM status |
| `GET /sim/state` | status, tick, speed, seed, day, season, population |
| `POST /sim/start` · `/sim/pause` · `/sim/step {n}` · `/sim/speed {multiplier}` | control |
| `POST /sim/reset {seed?, config?, preset?}` | new world |
| `GET/PUT /sim/config` | `WorldConfig` (population, tribes, scarcity, payoffs, strategy mix %, llm agents, mutation, noise) |
| `GET /sim/presets` | named presets |
| `GET /world/terrain` | heightmap + biome map |
| `GET /agents` · `GET /agents/{id}` | list / full detail (traits, needs, memory, trust, decision trace, LLM log) |
| `GET /tribes` · `GET /tribes/{id}` | tribes |
| `GET /metrics?from_tick=` | time series |
| `GET /events?limit=&type=` | event log |
| `POST /snapshots` · `GET /snapshots` · `POST /snapshots/{id}/load` | save/load |
| `GET /llm/status` · `GET /llm/stats` · `PUT /llm/settings` | LLM control |
| `POST /god/{action}` | drop food, drought, plague, spawn agent(strategy), smite |

WebSocket `/ws/world` (typed envelopes `{type, tick, data}`):
| Direction | Type | Content |
|---|---|---|
| S→C | `hello` | config, terrain meta, legend |
| S→C | `frame` | compact agent arrays `[id, x, z, heading, state, tribe, flags]`, resource deltas, time-of-day |
| S→C | `events` | batched events (birth, death, betrayal, alliance, war, coup…) |
| S→C | `metrics` | every N ticks |
| S→C | `speech` | LLM `say` lines, emoji state changes |
| S→C | `agent_detail` | for the subscribed agent only |
| C→S | `subscribe_agent`, `unsubscribe_agent`, `ping` | |

Serializer behind an interface (JSON now, msgpack later).

---

## 9. Frontend

### 9.1 Stack & structure
Vite · React · TypeScript strict · @react-three/fiber · @react-three/drei · @react-three/postprocessing · zustand · Tailwind · uPlot (charts) · openapi-typescript (generated DTO types).
```
frontend/src/
  app/       App.tsx, layout, providers
  api/       rest.ts, ws.ts (reconnect + backoff), generated types
  state/     simStore, selectionStore, uiStore, settingsStore
  scene/     World, Terrain, Water, Vegetation (instanced), Resources, Agents (InstancedMesh),
             Camps, Lighting (day/night), CameraRig, Effects, SpeechBubbles,
             overlays/ TrustLines, Territories, Heatmap
  ui/        TopBar, ControlBar, Inspector, EventFeed, ChartsPanel, ConfigDialog,
             LlmPanel, Minimap, Legend, HelpOverlay, Toasts
  lib/       interpolation, colors, math, keybindings
```

### 9.2 Visual style — "soft toy diorama", NOT voxel
- Smooth-shaded rolling island, pastel palette, warm sun + hemisphere light, soft shadows, light fog, optional SSAO/bloom.
- Agents: rounded bean/capsule bodies with two dot eyes, tribe color, size by age, leader headband/crown, LLM agents have a soft glowing halo. Squash-and-stretch bob when walking.
- State icon above head (emoji sprite): 🍖 💧 😴 ⚔️ 🤝 🗣️ 🕵️ 💔 👑.
- Trees = spheres on trunks, bushes = sphere clusters with berries, rocks = smooth icospheres, animated water shader, dome huts + campfire glow at night.

### 9.3 Controls
| Input | Action |
|---|---|
| Mouse wheel / pinch | zoom (clamped) |
| Right-drag / left-drag | orbit / pan |
| W A S D / arrows | pan · Q/E rotate |
| Click agent | select → Inspector · double-click = focus |
| F / Esc | follow selected / stop follow |
| Space | play/pause |
| 1–8 | speed presets (1× … MAX) |
| `.` | step one tick |
| R | reset (confirm dialog with seed + preset) |
| T / G / H / N / B | toggle trust lines / territories / heatmap / names / speech bubbles |
| ? | help overlay |

### 9.4 Panels
- **Inspector:** needs bars, traits radar, strategy, tribe/role, current skill + decision trace, top relationships, recent memories, LLM thoughts & plan (LLM agents).
- **Charts:** population by tribe, strategy share over time, cooperation rate per game, avg payoff per strategy, food Gini, betrayals/alliances.
- **Event feed:** filterable, click event → camera flies to location.
- **LLM monitor:** provider, model, queue length, calls/min, latency, failures, last prompts/responses.
- **New world dialog:** presets + sliders.
- Quality setting (low/med/high), FPS counter, minimap, screenshot button.

### 9.5 Performance
InstancedMesh for agents & vegetation; interpolate positions between frames; target 60 FPS at 500 agents on mid hardware; only the selected agent gets detailed data.

---

## 10. Metrics
Every N ticks: population (total / by tribe / by strategy), births, deaths by cause, cooperation rate per game type, average payoff per strategy, food Gini, trust-graph density, alliances, wars, betrayals, lies told / caught, LLM calls. Stored in SQLite, streamed via WS.

"Every N ticks" means *at least* N ticks have elapsed since the last sample — not `tick % N == 0`. Sampling runs on the broadcast thread (so the engine never pays for it), and the broadcast only sees the ticks that land on a 20 Hz frame; at 25× those are ~12 ticks apart, so a divisibility test misses nearly every window. Coups are reported as attempts and successes separately — most challenges fail. See ADR 0003.

**As built (Phase 5).** The simulation never awaits a model: the engine thread posts a plain-data `PromptContext` into an `IntentionBroker` and collects whatever has come back since the last tick, while an `LLMPump` on the event loop does all the waiting. A returned `Intention` *biases* utility scores (+0.35 for 45 sim-seconds) rather than choosing an action, so a starving schemer still eats first and switching the model off mid-run changes nothing but the absence of a thought. Replies are stamped with the world uid and dropped if the world was rebuilt meanwhile. Above the speed threshold the service stretches or suspends deliberation. Default provider is an in-process deterministic mock, so no model need be installed. See ADR 0004.

## 11. Persistence
SQLite (SQLModel) in `./data/gametheory.db` (Docker volume): runs, metrics, snapshots (full world state JSON, gzipped), capped events table.

## 12. Configuration
`backend/config/default.yaml` + `payoffs.yaml` + `presets/*.yaml`; env overrides via pydantic-settings (`.env`). Keys: `SIM_SEED`, `SIM_TICK_RATE`, `SIM_MAX_AGENTS`, `LLM_*` (see §7.5), `OLLAMA_URL` (default `http://localhost:11434`; backend in Docker + native Ollama → `http://host.docker.internal:11434`; compose `llm` profile → `http://ollama:11434`), `OLLAMA_MODEL` (default `qwen3:8b`; smaller GPU: `qwen3:4b`).

Presets: Peaceful Eden · Harsh Winter · Liars' Island · Tribal Wars · Axelrod Tournament · LLM Schemers.

## 13. Quality
- Backend: ruff (lint+format), mypy, pytest + pytest-asyncio + respx (fake Ollama HTTP), hypothesis for payoff/strategy properties, import-linter for layering. ≥ 80% coverage on `sim/` and `ai/` (excluding providers).
- Frontend: ESLint + Prettier, `tsc --noEmit`, vitest for stores/lib, Playwright smoke tests (loads, canvas renders, controls change sim state).
- structlog JSON logs with tick numbers. ADRs in `docs/adr/`.

## 14. Containers & local dev
`docker-compose.yml`:
| Service | Image | Port | Notes |
|---|---|---|---|
| backend | python:3.12-slim + uv | 8000 | dev target: bind mount + `--reload` |
| frontend | node LTS alpine | 5173 | dev: Vite `--host`; prod target: static build behind nginx |
| ollama | ollama/ollama | 11434 | **profile `llm`, optional**; volume for models; GPU block commented |

- Default on Windows: run Ollama natively (simpler GPU), backend reaches it via `host.docker.internal`.
- Also runnable without Docker from PyCharm: `uv run uvicorn …` + `npm run dev`; Vite proxies `/api` and `/ws` to `:8000`.
- PyCharm shared run configurations in `.run/` (Backend, Frontend, Backend tests, All via compose).
- `scripts/dev.ps1` starts backend + frontend in two windows.
