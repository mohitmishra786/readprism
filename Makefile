.PHONY: extract-eval starter-pack-check up-lite up-full build-lite backup restore demo docs-serve

starter-pack-check:
	cd backend && PYTHONPATH=. python3 scripts/check_starter_packs.py

up-lite:
	docker compose up -d --build

up-full:
	docker compose --profile full up -d --build

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
