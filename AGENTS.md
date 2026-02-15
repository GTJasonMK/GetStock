# Repository Guidelines

## Project Structure & Module Organization

- `app/`: FastAPI backend
  - `app/api/`: API routers (`/api/v1/*`)
  - `app/schemas/`: Pydantic v2 request/response models
  - `app/models/`: SQLAlchemy models (SQLite by default)
  - `app/services/`: business logic
  - `app/datasources/`: external market/news data clients
  - `app/llm/`: LLM client + agent orchestration
- `frontend/`: Next.js (App Router) UI
  - `frontend/src/app/`: routes/pages
  - `frontend/src/components/`: UI + panels
  - `frontend/src/lib/`: API client and helpers
- `tests/`: pytest suite for the backend
- `data/`: local runtime artifacts (e.g., `stock.db`, `scheduler.lock`)
- `docs/` and `design-system/`: design/architecture notes

## Build, Test, and Development Commands

- Install everything: `python install.py` (creates `.venv`, installs backend + frontend deps; Playwright optional)
- Run locally (backend + frontend): `python start.py`
  - Defaults: backend `http://localhost:8001`, frontend `http://localhost:3001`
  - Override ports: `BACKEND_PORT=8001 FRONTEND_PORT=3001 python start.py`
  - Windows shortcuts: `install.bat` / `start.bat` (backend hot-reload defaults off; set `BACKEND_RELOAD=true` to enable)
- Backend only: `uvicorn app.main:app --reload --port 8001`
- Frontend only: `cd frontend && npm install && npm run dev -- --port 3001`
- Frontend lint/build: `cd frontend && npm run lint` / `npm run build`

## Coding Style & Naming Conventions

- Python: 4-space indentation, type hints encouraged, prefer `async` endpoints/services, keep I/O shapes in `app/schemas/`.
- TypeScript/React: `strict: true`; components use `PascalCase` (e.g., `StockDetail.tsx`); path alias `@/*` → `frontend/src/*`.
- Don’t commit generated/runtime output: `.venv/`, `frontend/node_modules/`, `frontend/.next/`, `data/*.db`.

## Testing Guidelines

- Framework: `pytest` + `pytest-asyncio` (see `pytest.ini`).
- Naming: `tests/test_*.py`, `Test*` classes, `test_*` functions.
- Run: `pytest` (from the backend virtualenv).

## Commit & Pull Request Guidelines

- Git history is currently minimal (`init`), so no strong convention is established yet.
- Recommended: Conventional Commits (e.g., `feat(frontend): add market panel`, `fix(app): handle datasource timeout`).
- PRs should include: clear description, linked issue (if any), and screenshots for UI changes; ensure `pytest` and `npm run lint` pass.
