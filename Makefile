.PHONY: extract-eval

extract-eval:
	cd backend && PYTHONPATH=. python3 scripts/extract_eval.py

eval:
	cd backend && PYTHONPATH=. python3 scripts/rank_eval.py

retrieval-eval:
	cd backend && PYTHONPATH=. python3 scripts/retrieval_eval.py
