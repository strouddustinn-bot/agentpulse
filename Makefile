# AgentPulse developer commands
# Prerequisites: Python 3.10+, Node.js 22+

PYTHON := python3

.PHONY: help agent-test packaging-test agent-lint agent-config-validate dashboard-install dashboard-build \
        cp-install cp-test cp-typecheck contracts-validate clean

help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "%-24s %s\n", $$1, $$2}'

agent-test: ## Run local agent tests
	cd agent && $(PYTHON) tools/run_tests.py

packaging-test: ## Build wheel and run packaging integrity tests
	$(PYTHON) -m unittest tests.test_packaging -v
	$(PYTHON) scripts/check-launchd-plist.py
	bash -n scripts/install-agent.sh scripts/upgrade-agent.sh scripts/rollback-agent.sh scripts/smoke-test.sh docs/install.sh

agent-lint: ## Lint local agent code
	ruff check agent/

agent-config-validate: ## Validate the example agent configuration
	$(PYTHON) -c "import json, jsonschema; cfg=json.load(open('agent/agentpulse.config.example.json')); schema=json.load(open('configs/agentpulse.config.schema.json')); jsonschema.validate(cfg, schema); print('Agent config: PASS')"

dashboard-install: ## Install dashboard dependencies
	cd dashboard && npm ci

dashboard-build: ## Build the single React dashboard
	cd dashboard && npm run build

cp-install: ## Install Cloudflare Worker dependencies
	cd control-plane && npm ci

cp-test: ## Run Worker tests
	cd control-plane && npm test

cp-typecheck: ## Type-check Worker and generated bindings
	cd control-plane && npm run typecheck && npm run types:check

contracts-validate: ## Validate OpenAPI, schemas, refs, and fixtures
	$(PYTHON) scripts/validate-contracts.py

clean: ## Remove local build artifacts and caches
	find . -type d \( -name __pycache__ -o -name .pytest_cache -o -name node_modules -o -name dist \) -prune -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name '*.pyc' -delete 2>/dev/null || true
