# Game Theory — instructions for Claude Code

## What this is
A 3D autonomous society simulation (game theory · survival · manipulation · tribes) that runs on localhost
and is viewed in the browser. Full design: `docs/SPEC.md` — read only the sections the current task names.

## Stack
- **Backend:** Python 3.12, FastAPI, uvicorn, pydantic v2 + pydantic-settings, numpy, SQLModel/SQLite, httpx, jinja2, structlog. Package manager: **uv**.
- **Frontend:** Vite, React, TypeScript (strict), @react-three/fiber, @react-three/drei, @react-three/postprocessing, zustand, Tailwind, uPlot, openapi-typescript.
- **AI:** utility AI + game-theory strategies (always on) + optional local LLM via **Ollama** (MockProvider fallback).
- **Infra:** docker compose (backend, frontend, optional `ollama` profile). Windows 11 host, PyCharm, PowerShell.

## Layout
```
GameTheory/
  CLAUDE.md  README.md  docker-compose.yml  .env.example  .run/  scripts/dev.ps1
  docs/      SPEC.md  adr/
  backend/   pyproject.toml  Dockerfile  config/  app/{api,services,sim,ai,persistence,core,tools}  tests/
  frontend/  package.json  Dockerfile  vite.config.ts  src/{app,api,state,scene,ui,lib}  tests/
  data/      (gitignored, SQLite + snapshots)
```

## Commands (PowerShell)
```powershell
# backend (cd backend)
uv sync
uv run uvicorn app.main:app --reload --port 8000
uv run pytest -q                       # or a single file: uv run pytest tests/sim/test_x.py -q
uv run ruff check . ; uv run ruff format . ; uv run mypy app
uv run python -m app.tools.bench --agents 500 --ticks 2000
# frontend (cd frontend)
npm install ; npm run dev              # http://localhost:5173
npm run typecheck ; npm run lint ; npm run test ; npm run e2e
npm run gen:api                        # regenerate TS types from http://localhost:8000/openapi.json
# docker (repo root)
docker compose up --build
docker compose --profile llm up --build   # with containerized Ollama
```

## Architecture rules
1. `sim/` is pure: no FastAPI, no network, no persistence, no wall-clock time, no global RNG — inject clock and seeded `numpy.random.Generator`.
2. `api/` is transport only. It calls `services/`; it never mutates sim state directly.
3. LLM access only through `ai/llm` `LLMGateway`/`LLMProvider`. The simulation never awaits an LLM call.
4. One responsibility per class; files ≲ 300 lines; constructor DI; no module-level mutable state.
5. Fully typed (mypy, TS strict). Every API payload is a pydantic DTO; frontend types are generated, not hand-written.
6. Every new Skill is registered in `SkillRegistry` and has a unit test (preconditions + effect).
7. Same seed + LLM off ⇒ identical world after N ticks (keep the determinism test green).
8. Hot paths (needs decay, movement, neighbor search) use numpy / spatial hash; no O(n²) loops over all agents.
9. Visual style: rounded, soft, pastel "toy diorama". Never voxel/blocky.

## Hard rules — cost, safety, usage
- **Never** add paid or cloud AI services (OpenAI, Anthropic, Gemini, OpenRouter, etc.), API keys, billing, or anything that needs a credit card. Only `OllamaProvider` (localhost) and `MockProvider`.
- No runtime network calls except to Ollama on the configured URL. No analytics/telemetry.
- Don't install Ollama or pull models — print the exact commands for the user instead.
- Don't delete `data/`, run `docker system prune`, or force-push without asking.
- Keep token usage lean: work only on the current phase; read files you need, not the whole repo; run targeted tests after small edits and the full suite once at the end of a phase; never start long-running watch/dev servers in the foreground — use background mode or ask the user to run them.

## Definition of done (each phase)
- `ruff`, `mypy`, `tsc`, `eslint` clean; relevant tests pass.
- README / SPEC / ADR updated if behavior or architecture changed.
- End with: what changed, how to run it, what to check in the browser, known gaps. Then stop — don't start the next phase.
