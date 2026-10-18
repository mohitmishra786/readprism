.PHONY: up-build extract-eval starter-pack-check env up up-lite up-full up-dev build-lite backup restore demo docs-serve test-services test-services-down test-backend test

test-services:
	docker compose -f docker-compose.test.yml up -d

test-services-down:
	docker compose -f docker-compose.test.yml down -v

test-backend: test-services
	cd backend && pytest

test: test-backend

starter-pack-check:
	cd backend && PYTHONPATH=. python3 scripts/check_starter_packs.py

env:
	./scripts/init_env.sh

up: env
	docker compose up -d

up-lite: env
	READPRISM_VERSION=latest-lite docker compose up -d

up-full: env
	docker compose --profile full up -d

# Local development: APP_ENV=development, --reload, source mounts.
up-dev: env
	docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build

# Build from this checkout (no source mounts) instead of pulling GHCR images.
up-build: env
	docker compose -f docker-compose.yml -f docker-compose.build.yml up -d --build

build-lite:
	docker compose -f docker-compose.yml -f docker-compose.build.yml build --build-arg LITE=1 backend

backup:
	./scripts/backup.sh

restore:
	./scripts/restore.sh $(FILE)

demo:
	cd backend && PYTHONPATH=. python3 scripts/seed_demo.py

docs-serve:
	mkdocs serve
