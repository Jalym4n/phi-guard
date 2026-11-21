.PHONY: install test lint eval eval-quick studio-ui studio

install:
	pip install -e ".[dev,studio,eval]"

test:
	pytest --cov --cov-report=term

lint:
	ruff check . && ruff format --check . && mypy

# Regenerates the synthetic dataset and every number in eval/RESULTS.md.
eval:
	python -m eval.generate && python -m eval.run && python -m eval.ocr_eval

eval-quick:
	python -m eval.generate --quick --out /tmp/phi-guard-eval && python -m eval.run --quick

studio-ui:
	cd studio-ui && npm ci && npm run build

studio:
	phi-guard-studio
