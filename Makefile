.DEFAULT_GOAL := help
SHELL := /usr/bin/env bash

MODE ?= container
SCENARIO ?= all
REPORT ?= artifacts/comparison-report.json

GITLEAKS         ?= gitleaks
LEFTHOOK_VERSION ?= 1.7.10
LEFTHOOK_DIR     ?= $(CURDIR)/.bin
LEFTHOOK_BIN     ?= $(LEFTHOOK_DIR)/lefthook

.PHONY: help
help: ## Show help
	@awk 'BEGIN {FS = ":.*##"} /^[a-zA-Z_-]+:.*##/ {printf "\033[36m%-22s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

.PHONY: env
env: ## Create local virtual environment for harness
	uv venv .venv
	@echo "Activate with: . .venv/bin/activate"

.PHONY: install
install: ## Install harness dependencies
	uv sync --extra dev

.PHONY: fmt
fmt: ## Format code in place (ruff format)
	uv run ruff format .

.PHONY: lint
lint: ## Run lint/type checks
	uv run ruff check .
	uv run ruff format --check .
	uv run mypy

.PHONY: validate
validate: ## Static type checking (mypy)
	uv run mypy

.PHONY: plan
plan: ## Not applicable — use 'make validate' or 'make test' for Python repos
	@echo "INFO: 'plan' is Terraform-specific and does not apply to Python repos."
	@echo "      To type-check: make validate"
	@echo "      To run tests: make test"

.PHONY: test
test: ## Run unit/smoke tests
	uv run pytest

.PHONY: check
check: lint test ## Run full local quality gate

.PHONY: compare
compare: ## Run full comparison suite (set MODE=container|native)
	env -u VIRTUAL_ENV uv run --project . python -m orchestrator.main --mode "$(MODE)" --scenario "$(SCENARIO)" --checks parity,property,perf --report-out "$(REPORT)"

.PHONY: report
report: ## Run comparison and generate JSON report (set MODE/SCENARIO/REPORT)
	$(MAKE) compare MODE="$(MODE)" SCENARIO="$(SCENARIO)" REPORT="$(REPORT)"

.PHONY: compare-container
compare-container: ## Run comparison in container mode
	$(MAKE) compare MODE=container

.PHONY: compare-native
compare-native: ## Run comparison in native mode
	$(MAKE) compare MODE=native

.PHONY: compare-native-sepal
compare-native-sepal: ## Run native comparison for the sepal-sum scenario
	$(MAKE) compare MODE=native SCENARIO=sepal-sum

.PHONY: compare-native-triple
compare-native-triple: ## Run native 3-way comparison (python-sklearn, python-onnx, rust-onnx)
	$(MAKE) compare MODE=native SCENARIO=sepal-sum

.PHONY: compare-native-raw-all
compare-native-raw-all: ## Run native 5-way comparison (python onnx/sklearn/pytorch/tensorflow + rust onnx)
	$(MAKE) compare MODE=native SCENARIO=raw-all-frameworks

.PHONY: secrets-scan-staged lefthook-bootstrap lefthook-install lefthook-run lefthook

secrets-scan-staged: ## Scan staged diff for secrets
	@command -v $(GITLEAKS) >/dev/null 2>&1 || (echo "Missing tool: $(GITLEAKS). Install: https://github.com/gitleaks/gitleaks#installing" && exit 1)
	$(GITLEAKS) protect --staged --redact

lefthook-bootstrap: ## Download lefthook binary into ./.bin
	LEFTHOOK_VERSION="$(LEFTHOOK_VERSION)" BIN_DIR="$(LEFTHOOK_DIR)" bash ./scripts/bootstrap_lefthook.sh

lefthook-install: lefthook-bootstrap ## Install git hooks (runs bootstrap first)
	@if [ -x "$(LEFTHOOK_BIN)" ] && [ -x ".git/hooks/pre-commit" ] && [ -x ".git/hooks/pre-push" ] && [ -x ".git/hooks/commit-msg" ]; then \
		echo "lefthook hooks already installed"; \
		exit 0; \
	fi
	LEFTHOOK="$(LEFTHOOK_BIN)" "$(LEFTHOOK_BIN)" install

lefthook-run: lefthook-bootstrap ## Run all hooks locally (pre-commit + commit-msg + pre-push)
	LEFTHOOK="$(LEFTHOOK_BIN)" "$(LEFTHOOK_BIN)" run pre-commit
	@tmp_msg="$$(mktemp)"; \
	echo "chore(hooks): validate commit-msg hook" > "$$tmp_msg"; \
	LEFTHOOK="$(LEFTHOOK_BIN)" "$(LEFTHOOK_BIN)" run commit-msg -- "$$tmp_msg"; \
	rm -f "$$tmp_msg"
	LEFTHOOK="$(LEFTHOOK_BIN)" "$(LEFTHOOK_BIN)" run pre-push

lefthook: lefthook-bootstrap lefthook-install lefthook-run ## Install hooks and run them

# ── Standard quality-system targets ──────────────────────────────────────────
SRC_DIR  ?= orchestrator
TEST_DIR ?= tests

.PHONY: fmt-check
fmt-check: ## Check formatting (no changes)
	uv run ruff format --check .
	uv run ruff check .

.PHONY: typecheck
typecheck: ## Type-check with mypy
	uv run mypy

.PHONY: test-all
test-all: ## Run full test suite
	uv run pytest tests/

.PHONY: test-property
test-property: ## Run Hypothesis property-based tests
	uv run pytest -q -k "hypothesis or property" tests/ 2>/dev/null || true

.PHONY: coverage
coverage: ## Run tests with coverage report
	uv run pytest --cov=$(SRC_DIR) --cov-report=term-missing \
	  --cov-report=xml:coverage.xml $(TEST_DIR)

.PHONY: mutation-test
mutation-test: ## Run mutation testing with mutmut (slow — run in CI)
	uv run mutmut run --paths-to-mutate=$(SRC_DIR) --tests-dir=$(TEST_DIR) || true
	uv run mutmut results

.PHONY: clean
clean: ## Remove caches and build artifacts
	rm -rf .venv .pytest_cache .mypy_cache .ruff_cache .coverage htmlcov coverage.xml artifacts/
	find . -type d -name '__pycache__' -exec rm -r {} +
	find . -type f -name '*.py[cod]' -delete

PLATFORM_STANDARDS_SHA ?= 3c787edb4e96ddea2e86b2add2c32139685e8db7  # v1.2.1
PLATFORM_STANDARDS_RAW ?= https://raw.githubusercontent.com/FelipeFuhr/ffreis-platform-standards

install-act: ## Download pinned act binary into .bin/
	@mkdir -p scripts
	@curl -fsSL "$(PLATFORM_STANDARDS_RAW)/$(PLATFORM_STANDARDS_SHA)/scripts/install_act.sh" \
		-o scripts/install_act.sh && chmod +x scripts/install_act.sh
	@bash ./scripts/install_act.sh

ci-local: ## Run workflows locally via act (GH Actions quota fallback). Args via ARGS=...
	@mkdir -p scripts
	@curl -fsSL "https://raw.githubusercontent.com/FelipeFuhr/ffreis-platform-ci-local/v1.0.0/scripts/run-ci-local.sh" \
		-o scripts/run-ci-local.sh && chmod +x scripts/run-ci-local.sh
	@CI_LOCAL_FINDINGS_REF=v1.0.0 PATH="$(CURDIR)/.bin:$(PATH)" bash ./scripts/run-ci-local.sh $(ARGS)
