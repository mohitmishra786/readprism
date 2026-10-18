.PHONY: extract-eval starter-pack-check env up up-lite up-full up-dev build-lite backup restore demo docs-serve

starter-pack-check:
	cd backend && PYTHONPATH=. python3 scripts/check_starter_packs.py

env:
	./scripts/init_env.sh

up: env
	docker compose up -d --build

up-lite: env
	docker compose build --build-arg LITE=1 backend
	docker compose up -d

up-full: env
	docker compose --profile full up -d --build

# Local development: APP_ENV=development, --reload, source mounts.
up-dev: env
	docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build

build-lite:
	docker compose build --build-arg LITE=1 backend

backup:
	./scripts/backup.sh

restore:
	./scripts/restore.sh $(FILE)

demo:
	cd backend && PYTHONPATH=. python3 scripts/seed_demo.py

docs-serve:
	mkdocs serve
