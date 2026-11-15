# Every target runs inside Docker. The host needs only Docker and make.
# Usage: `make help`.

COMPOSE ?= docker compose
# PROD=1 runs a target against the production stack (compose.prod.yaml), for example
# `make bootstrap PROD=1 EMAIL=…` or `make backup PROD=1`.
ifeq ($(PROD),1)
COMPOSE := docker compose -f compose.yaml -f compose.prod.yaml
endif
PROD_COMPOSE := docker compose -f compose.yaml -f compose.prod.yaml
BACKUP_DIR ?= backups
# One-off commands start only db and redis (not the migrate service), so they also
# work before migrations exist. Tests create their own test database.
DEPS    := $(COMPOSE) up -d --wait db redis
RUN     := $(DEPS) && $(COMPOSE) run --rm --no-deps api
MANAGE  := $(RUN) python manage.py
ARGS    ?=

.DEFAULT_GOAL := help
.PHONY: help env build up down logs ps lock migrate makemigrations shell manage test-live parse-receipt sanitize-fixture \
        bootstrap superuser test lint fmt fmt-check typecheck check clean \
        prod-up prod-down prod-logs prod-ps prod-ca backup restore

help: ## Show this help
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

env: ## Create .env from .env.example if it does not exist
	@test -f .env || (cp .env.example .env && echo "Created .env from .env.example")

build: env ## Build the backend images
	$(COMPOSE) build

up: env ## Start the dev stack (db, redis, migrate, api, worker, beat)
	$(COMPOSE) up -d --build
	@echo "API: http://localhost:8000  Swagger: http://localhost:8000/api/docs/"

down: ## Stop the dev stack
	$(COMPOSE) down

logs: ## Follow logs (ARGS="api worker" to filter)
	$(COMPOSE) logs -f $(ARGS)

ps: ## Show service status
	$(COMPOSE) ps

lock: ## Resolve dependencies and write backend/uv.lock (in a container)
	docker build --target base -t eksoda-backend:base ./backend
	docker run --rm -v "$(CURDIR)/backend:/app" -w /app eksoda-backend:base uv lock $(ARGS)

migrate: env ## Apply migrations
	$(MANAGE) migrate $(ARGS)

makemigrations: env ## Create migrations (ARGS="app_label" to limit)
	$(MANAGE) makemigrations $(ARGS)

shell: env ## Django shell
	$(MANAGE) shell

manage: env ## Run any manage.py command: make manage ARGS="check --deploy"
	$(MANAGE) $(ARGS)

bootstrap: env ## Create the first owner: make bootstrap EMAIL=you@example.com HOUSEHOLD="Home"
	$(MANAGE) bootstrap_household --email "$(EMAIL)" --household "$(HOUSEHOLD)" $(ARGS)

superuser: env ## Create a Django admin superuser
	$(MANAGE) createsuperuser

test: env ## Run tests (ARGS="tests/accounts -k login")
	$(RUN) pytest $(ARGS)

test-live: env ## Opt-in live tests against real sources: make test-live URLS="<url> <url>"
	$(DEPS) && $(COMPOSE) run --rm --no-deps -e RUN_LIVE_TESTS=1 -e LIVE_RECEIPT_URLS="$(URLS)" api pytest -m live -p no:cacheprovider -v $(ARGS)

parse-receipt: env ## Parse a receipt URL or saved page (no database): make parse-receipt SRC=<url|backend-relative path> ARGS=--json
	$(MANAGE) parse_receipt "$(SRC)" $(ARGS)

sanitize-fixture: env ## Sanitize a saved page: make sanitize-fixture PROVIDER=impact IN=/abs/raw.html OUT=tests/fixtures/impact/name.html
	$(DEPS) && $(COMPOSE) run --rm --no-deps -v "$(dir $(abspath $(IN))):/raw:ro" api python manage.py sanitize_fixture "$(PROVIDER)" "/raw/$(notdir $(IN))" "$(OUT)" $(ARGS)

lint: env ## Lint with ruff
	$(RUN) ruff check . $(ARGS)

fmt: env ## Format with ruff
	$(RUN) sh -c "ruff format . && ruff check --fix ."

fmt-check: env ## Check formatting
	$(RUN) ruff format --check .

typecheck: env ## Type-check with mypy (informational for now)
	$(RUN) mypy apps config

check: env ## Everything that must pass before a task is done
	$(RUN) sh -c "ruff check . && ruff format --check . && python manage.py makemigrations --check --dry-run && pytest --cov --cov-report=term-missing:skip-covered $(ARGS)"

prod-up: env ## Build and start the production stack (proxy, backups): docs/deployment.md
	$(PROD_COMPOSE) up -d --build --remove-orphans

prod-down: ## Stop the production stack (volumes are kept)
	$(PROD_COMPOSE) down

prod-logs: ## Follow production logs (ARGS="api worker" to filter)
	$(PROD_COMPOSE) logs -f $(ARGS)

prod-ps: ## Show production service status
	$(PROD_COMPOSE) ps

CA_FILE ?= eksoda-root-ca.crt
prod-ca: ## Export the proxy's local root CA certificate (install it on each client device)
	$(PROD_COMPOSE) cp proxy:/data/caddy/pki/authorities/local/root.crt "$(CA_FILE)"
	@echo "Wrote $(CA_FILE). Install it as a trusted CA on phones and computers (docs/deployment.md §3)."
	@command -v openssl >/dev/null && openssl x509 -in "$(CA_FILE)" -noout -subject -enddate -fingerprint -sha256 || true

backup: ## Dump the database now into BACKUP_DIR (default backups/); PROD=1 for production
	@mkdir -p "$(BACKUP_DIR)"
	@umask 077; f="$(BACKUP_DIR)/eksoda-$$(date -u +%Y%m%d-%H%M%S).dump"; \
	if $(COMPOSE) exec -T db sh -c 'pg_dump -U "$$POSTGRES_USER" -d "$$POSTGRES_DB" -Fc' > "$$f.partial"; then \
		mv "$$f.partial" "$$f" && echo "Wrote $$f"; \
	else rm -f "$$f.partial"; echo "Backup failed"; exit 1; fi

restore: ## Replace the database with a dump: make restore FILE=backups/x.dump CONFIRM=yes [PROD=1]
	@test -f "$(FILE)" || (echo "FILE=<path to a .dump> is required"; exit 1)
	@test "$(CONFIRM)" = yes || (echo "This REPLACES the whole database with $(FILE). Re-run with CONFIRM=yes."; exit 1)
	@echo "Taking a safety backup of the current database first"
	$(MAKE) backup
	$(COMPOSE) stop api worker beat
	$(COMPOSE) exec -T db sh -c 'dropdb -U "$$POSTGRES_USER" --force --if-exists "$$POSTGRES_DB" && createdb -U "$$POSTGRES_USER" "$$POSTGRES_DB"'
	$(COMPOSE) exec -T db sh -c 'pg_restore -U "$$POSTGRES_USER" -d "$$POSTGRES_DB" --no-owner --exit-on-error --single-transaction' < "$(FILE)"
	$(COMPOSE) up -d
	@echo "Restored $(FILE). The migrate service applied any newer migrations."

clean: ## Stop the stack and delete its volumes (DESTROYS the dev database)
	$(COMPOSE) down -v
