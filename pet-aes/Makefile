.PHONY: install
install: ## Install the virtual environment and install the pre-commit hooks
	@echo "Creating virtual environment using uv"
	@uv sync
	@uv run pre-commit install

.PHONY: check
check: ## Run code quality tools
	@echo "Checking lock file consistency with 'pyproject.toml'"
	@uv lock --locked
	@echo "Linting code: Running pre-commit"
	@uv run pre-commit run -a
	@echo "Static type checking: Running mypy"
	@uv run mypy
	@echo "Checking for obsolete dependencies: Running deptry"
	@uv run deptry src

.PHONY: test
test: ## Test the code with pytest
	@echo "Testing code: Running pytest"
	@uv run python -m pytest --cov --cov-config=pyproject.toml --cov-report=xml

.PHONY: audit
audit: ## Check the locked dependency tree against the advisory database
	@uv audit --locked

.PHONY: bump
bump: ## Bump the version and changelog from conventional commits, and tag the release
	@# Deliberately not a plain `cz bump`: that commits before the lockfile is
	@# refreshed, and uv.lock records the project version, so the uv-lock hook
	@# rewrites it mid-commit and the bump aborts with no commit and no tag.
	@# Editing the files first, then re-locking, lets the commit pass every hook.
	@old="$$(uv run cz version --project)"; \
	uv run cz bump --changelog --yes --files-only && \
	uv lock && \
	new="$$(uv run cz version --project)"; \
	git add -A && \
	git commit -m "bump: version $$old -> $$new" && \
	git tag "v$$new" && \
	echo "Created v$$new. Review it, then: git push --follow-tags"

.PHONY: build
build: clean-build ## Build wheel file
	@echo "Creating wheel file"
	@uvx --from build pyproject-build --installer uv

.PHONY: clean-build
clean-build: ## Clean build artifacts
	@echo "Removing build artifacts"
	@uv run python -c "import shutil; import os; shutil.rmtree('dist') if os.path.exists('dist') else None"

.PHONY: docs-test
docs-test: ## Test if documentation can be built without warnings or errors
	@uv run mkdocs build -s

.PHONY: docs
docs: ## Build and serve the documentation
	@uv run mkdocs serve

.PHONY: help
help:
	@uv run python -c "import re; \
	[[print(f'\033[36m{m[0]:<20}\033[0m {m[1]}') for m in re.findall(r'^([a-zA-Z_-]+):.*?## (.*)$$', open(makefile).read(), re.M)] for makefile in ('$(MAKEFILE_LIST)').strip().split()]"

.DEFAULT_GOAL := help
