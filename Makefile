.DEFAULT_GOAL := help

.PHONY: help install install-dev lint format type-check test test-unit \
        test-cov clean docs docs-serve build

help: ## Show this help message
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

install: ## Install the package (production deps only)
	uv sync --no-dev

install-dev: ## Install all dependencies including dev tools
	uv sync
	pre-commit install

lint: ## Run ruff linter
	uv run ruff check src/ tests/

format: ## Run ruff formatter
	uv run ruff format src/ tests/

format-check: ## Check formatting without modifying files
	uv run ruff format --check src/ tests/

type-check: ## Run mypy type checker
	uv run mypy src/

test: ## Run unit tests
	uv run pytest tests/unit/ -v

test-unit: ## Run unit tests with coverage
	uv run pytest tests/unit/ --cov=src/younit --cov-report=term-missing --cov-report=html -v

test-cov: ## Run unit tests and open coverage report
	uv run pytest tests/unit/ --cov=src/younit --cov-report=html
	open htmlcov/index.html 2>/dev/null || start htmlcov/index.html 2>/dev/null || true

ci: lint format-check type-check test-unit ## Run all CI checks locally

clean: ## Remove build artifacts and caches
	rm -rf dist/ build/ *.egg-info/ htmlcov/ .coverage .coverage.* .pytest_cache/ .mypy_cache/ .ruff_cache/ site/

docs: ## Build documentation
	uv run mkdocs build

docs-serve: ## Serve documentation locally
	uv run mkdocs serve

build: ## Build wheel and sdist
	uv build

pre-commit: ## Run all pre-commit hooks
	pre-commit run --all-files
