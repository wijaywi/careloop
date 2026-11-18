PYTHON ?= python3
OUT ?= out

.PHONY: setup test demo simulate simulate-fast reproduce web-build clean-output

setup:
	$(PYTHON) -m venv .venv
	$(PYTHON) -m pip install --no-input --requirement requirements.lock
	cd web && npm ci --ignore-scripts --no-audit --no-fund

test:
	PYTHONPATH=. $(PYTHON) -B -m unittest discover -s tests -p 'test_*.py'
	cd web && npm test

demo:
	$(PYTHON) scripts/demo.py --output $(OUT)/demo.json

simulate-fast:
	$(PYTHON) -c "from pathlib import Path; Path('$(OUT)').mkdir(exist_ok=True)"
	PYTHONPATH=. $(PYTHON) -B -m careloop.simulator --bounded --cohort-size 50 --runs 2 --sensitivity --stress --seed 20261019 --json $(OUT)/simulate-fast.json --csv $(OUT)/simulate-fast.csv

simulate:
	$(PYTHON) -c "from pathlib import Path; Path('$(OUT)').mkdir(exist_ok=True)"
	PYTHONPATH=. $(PYTHON) -B -m careloop.simulator --full --json $(OUT)/simulation-full.json --csv $(OUT)/simulation-full.csv

reproduce:
	$(PYTHON) scripts/reproduce.py --output $(OUT)

web-build:
	cd web && npm run build

clean-output:
	$(PYTHON) -c "import shutil; shutil.rmtree('$(OUT)', ignore_errors=True)"
