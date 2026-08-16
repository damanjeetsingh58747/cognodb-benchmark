.PHONY: setup dataset benchmark results

setup:
	python3 -m venv .venv
	.venv/bin/python -m pip install -r requirements.txt

dataset:
	./scripts/download_dataset.sh
	python benchmark/prepare_dataset.py

benchmark:
	./scripts/run_all.sh

results:
	python benchmark/build_results.py
	python benchmark/build_analysis.py
	python benchmark/build_readme.py
