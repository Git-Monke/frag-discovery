# frag-discovery — dev commands
# Run `make` (or `make help`) to list targets.

.DEFAULT_GOAL := help

.PHONY: help install backend frontend test lint build clean sync-catalog

help: ## Show available commands
	@printf '\033[36m%s\033[0m\n' 'frag-discovery — dev commands'
	@printf '%s\n' '---------------------------------------------'
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

install: ## Install backend (uv sync) + frontend (npm install)
	cd frag-discovery-backend && uv sync
	cd frag-discovery-frontend && npm install

backend: ## FastAPI backend (auth + browse + discover) — http://localhost:8000
	cd frag-discovery-backend && uv run uvicorn app.main:app --reload --port 8000

sync-catalog: ## Symlink the frag-scraper catalog DB + note embeddings into backend data/
	mkdir -p frag-discovery-backend/data
	ln -sfn "$(CURDIR)/../frag-scraper/fragrances.db" frag-discovery-backend/data/fragrances.db
	ln -sfn "$(CURDIR)/../frag-scraper/experiments/note_embeddings/out" frag-discovery-backend/data/embeddings
	@echo 'Catalog + embeddings linked into frag-discovery-backend/data/'

frontend: ## Vite dev server — http://localhost:5173
	cd frag-discovery-frontend && npm run dev

test: ## Backend tests (pytest) + frontend typecheck/build
	cd frag-discovery-backend && uv run pytest
	cd frag-discovery-frontend && npm run build

lint: ## Frontend oxlint + backend ruff
	cd frag-discovery-frontend && npm run lint
	cd frag-discovery-backend && uvx ruff check app tests

build: ## Build the frontend for production
	cd frag-discovery-frontend && npm run build

clean: ## Remove frontend dist + backend Python caches
	rm -rf frag-discovery-frontend/dist
	find frag-discovery-backend -type d -name __pycache__ -prune -exec rm -rf {} +
