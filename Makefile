# Davis Weather Station - Development and Deployment
SHELL := /bin/bash
PYTHON := python3
PIP := pip3
NPM := npm

BACKEND_DIR := backend
FRONTEND_DIR := frontend
VENV_DIR := $(BACKEND_DIR)/.venv
VENV_PY := $(VENV_DIR)/bin/python
VENV_PIP := $(VENV_DIR)/bin/pip

.PHONY: help setup setup-backend setup-frontend dev dev-backend dev-frontend \
        build test test-backend clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ── Setup ─────────────────────────────────────────────────────

setup: setup-backend setup-frontend ## Install all dependencies

setup-backend: ## Create venv and install Python dependencies
	$(PYTHON) -m venv $(VENV_DIR)
	$(VENV_PIP) install --upgrade pip
	$(VENV_PIP) install -e "$(BACKEND_DIR)[dev]"

setup-frontend: ## Install npm dependencies
	cd $(FRONTEND_DIR) && $(NPM) install

# ── Development ───────────────────────────────────────────────

dev: ## Run backend and frontend dev servers together
	@echo "Starting backend (port 8000) and frontend (port 3000)..."
	@$(MAKE) -j2 dev-backend dev-frontend

dev-backend: ## Run FastAPI dev server with auto-reload
	cd $(BACKEND_DIR) && $(VENV_PY) -m uvicorn app.main:app \
		--host 0.0.0.0 --port 8000 --reload --log-level info

dev-frontend: ## Run Vite dev server with HMR
	cd $(FRONTEND_DIR) && $(NPM) run dev

# ── Build ─────────────────────────────────────────────────────

build: build-frontend ## Build frontend for production

build-frontend: ## Build frontend static files
	cd $(FRONTEND_DIR) && $(NPM) run build

# ── Run ───────────────────────────────────────────────────────

run: build ## Build frontend and run production server
	cd $(BACKEND_DIR) && $(VENV_PY) -m uvicorn app.main:app \
		--host 0.0.0.0 --port 8000 --log-level info

# ── Testing ───────────────────────────────────────────────────

test: test-backend ## Run all tests

test-backend: ## Run backend tests
	cd $(BACKEND_DIR) && $(VENV_PY) -m pytest ../tests/backend -v

# ── Cleanup ───────────────────────────────────────────────────

clean: ## Remove build artifacts and caches
	rm -rf $(FRONTEND_DIR)/dist
	rm -rf $(VENV_DIR)
	rm -rf $(FRONTEND_DIR)/node_modules
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
