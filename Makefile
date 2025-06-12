
VENV = .venv
PY3 = $(VENV)/bin/python3
TYPOS = $(VENV)/bin/typos

SRC = mpv-jellyfin-dmenu.py

.PHONLY: default
default: lint typos test

.PHONLY: lint
lint: $(PY3)
	$(PY3) -m black -l 99 $(SRC)
	$(PY3) -m flake8 $(SRC)
	$(PY3) -m pylint $(SRC)

.PHONLY: typos
typos: $(TYPOS)
	$(TYPOS) $(SRC)

.PHONLY: test
test: $(PY3)
	$(PY3) -m pytest $(SRC)

$(VENV)/bin/typos $(VENV)/bin/python3: $(VENV)/.make-installed-requirements-dev.txt

$(VENV)/.make-installed-requirements-dev.txt: requirements-dev.txt
	python3 -m venv $(VENV)
	$(VENV)/bin/pip install -r $<
	cp $< $@
