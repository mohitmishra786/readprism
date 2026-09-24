.PHONY: extract-eval

extract-eval:
	cd backend && PYTHONPATH=. python3 scripts/extract_eval.py
