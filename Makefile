.PHONY: extract-eval starter-pack-check

starter-pack-check:
	cd backend && PYTHONPATH=. python3 scripts/check_starter_packs.py

extract-eval:
	cd backend && PYTHONPATH=. python3 scripts/extract_eval.py

eval:
	cd backend && PYTHONPATH=. python3 scripts/rank_eval.py

retrieval-eval:
	cd backend && PYTHONPATH=. python3 scripts/retrieval_eval.py
