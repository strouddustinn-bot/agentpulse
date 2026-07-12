# Makefile — AgentPulse root-level developer commands
#
# Prerequisites: Python 3.10+, Node.js 22+, Docker (optional)
#
# Targets:
#   make help           Show all targets
#   make agent-test     Run agent unit tests
#   make backend-test    Run backend tests
#   make lint           Lint all components
#   make build          Build all containers
#   make up             Start full stack
#   make down           Stop all containers
#   make clean          Remove build artifacts
#   make install        Run install-agent.sh (requires sudo)
#   make bootstrap-dev  Run bootstrap-dev.sh

PYTHON      := python3
PYTEST      := pytest
PYTEST_ARGS := -v --tb=short -q
PYLINT      := ruff
PYLINT_ARGS := .

DOCKER_COMPOSE := docker compose
DC_FILES      := -f docker-compose.yml -f docker-compose.dev.yml

# ─── Colours ──────────────────────────────────────────────────────────────────
GREEN  := $(shell tput setaf 2 2>/dev/null || echo '')
YELLOW := $(shell tput setaf 3 2>/dev/null || echo '')
RESET  := $(shell tput sgr0 2>/dev/null || echo '')

# ─── Help ─────────────────────────────────────────────────────────────────────
.PHONY: help
help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "$(GREEN)%-20s$(RESET) %s\n", $$1, $$2}'

# ─── Agent ────────────────────────────────────────────────────────────────────
agent-test: ## Run agent unit tests
	cd agent && $(PYTHON) tools/run_tests.py

agent-lint: ## Lint agent Python code
	$(PYLINT) $(PYLINT_ARGS) agent/

agent-config-validate: ## Validate agent config JSON schema
	@python3 -c "import json, jsonschema; \
	  cfg = json.load(open('agent/agentpulse.config.example.json')); \
	  schema = json.load(open('configs/agentpulse.config.schema.json')); \
	  jsonschema.validate(cfg, schema); print('Valid')"

# ─── Backend ──────────────────────────────────────────────────────────────────
backend-test: ## Run backend tests
	cd backend && $(PYTEST) $(PYTEST_ARGS)

backend-lint: ## Lint backend Python code
	$(PYLINT) $(PYLINT_ARGS) backend/

# ─── Dashboard ────────────────────────────────────────────────────────────────
dashboard-test: ## Run dashboard frontend tests
	cd dashboard/web && npm test -- --run

dashboard-build: ## Build dashboard frontend
	cd dashboard/web && npm run build

dashboard-lint: ## Lint dashboard frontend
	cd dashboard/web && npm run lint

# ─── Control-plane ───────────────────────────────────────────────────────────
cp-test: ## Run control-plane tests
	cd control-plane && npm test

cp-typecheck: ## Type-check control-plane TypeScript
	cd control-plane && npm run typecheck

# ─── Contracts ───────────────────────────────────────────────────────────────
contracts-validate: ## Validate all JSON schemas against draft-07
	@python3 -c "import json, glob, jsonschema; \
	  schema = json.load(open('packages/contracts/schemas/agentpulse.config.schema.json')); \
	  for f in sorted(glob.glob('packages/contracts/schemas/*.json')): \
	    try: jsonschema.validate(json.load(open(f)), schema); print(f'OK: {f}') \
	    except Exception as e: print(f'FAIL: {f}: {e}')"

openapi-validate: ## Validate OpenAPI spec
	@python3 -c "import yaml; \
	  doc = yaml.safe_load(open('packages/contracts/openapi.yaml')); \
	  print('Valid YAML, paths:', len(doc.get('paths', {})), 'schemas:', \
	        len(doc.get('components', {}).get('schemas', {})))"

# ─── Docker ──────────────────────────────────────────────────────────────────
build: ## Build all Docker images
	$(DOCKER_COMPOSE) $(DC_FILES) build

up: ## Start full dev stack
	$(DOCKER_COMPOSE) $(DC_FILES) up -d

down: ## Stop all containers
	$(DOCKER_COMPOSE) $(DC_FILES) down

logs: ## Tail logs from all containers
	$(DOCKER_COMPOSE) $(DC_FILES) logs -f

# ─── Integration ──────────────────────────────────────────────────────────────
integration-test: ## Run integration tests
	@echo "Integration tests require running stack — run 'make up' first"
	cd tests/integration && $(PYTEST) $(PYTEST_ARGS) || true

# ─── Housekeeping ─────────────────────────────────────────────────────────────
clean: ## Remove build artifacts and caches
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name node_modules -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name '*.pyc' -delete 2>/dev/null || true
	cd dashboard/web && npm run build -- --clearScreen 2>/dev/null || true

.PHONY: help agent-test agent-lint agent-config-validate \
        backend-test backend-lint dashboard-test dashboard-build dashboard-lint \
        cp-test cp-typecheck contracts-validate openapi-validate \
        build up down logs integration-test clean
