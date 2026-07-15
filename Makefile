.PHONY: all kdebug kbit kentry kloc kberif kcov test full-test clean kcov-test sdk-test install-skill

PYTHON ?= python3
SKILL_NAME ?= kverif
SKILL_SRC ?= skill

all: kdebug kbit kentry kloc kberif kcov

kdebug:
	$(MAKE) -C kdebug

kbit:
	$(MAKE) -C kbit

kentry:
	$(MAKE) -C kentry

kloc:
	$(MAKE) -C kloc

kberif:
	$(MAKE) -C kberif

kcov:
	@true

kcov-test:
	$(MAKE) -C kcov PYTHON=$(PYTHON) test

sdk-test:
	PYTHONPATH=. $(PYTHON) -m pytest kverif_sdk/tests -q

install-skill:
	@set -eu; \
	src="$(SKILL_SRC)"; \
	name="$(SKILL_NAME)"; \
	ts=$$(date +%Y%m%d-%H%M%S); \
	if [ ! -f "$$src/SKILL.md" ]; then \
		echo "ERROR: missing $$src/SKILL.md"; \
		exit 1; \
	fi; \
	for home in "$$HOME/.codex" "$$HOME/.claude"; do \
		skills_dir="$$home/skills"; \
		dst="$$skills_dir/$$name"; \
		bak="$$home/$$name-skill.bak.$$ts"; \
		echo "==> Installing $$name skill into $$dst"; \
		mkdir -p "$$skills_dir"; \
		if [ -e "$$dst" ]; then \
			echo "    existing skill found: $$dst"; \
			echo "    moving existing skill to backup outside skills dir: $$bak"; \
			mv "$$dst" "$$bak"; \
		else \
			echo "    no existing $$name skill found in $$skills_dir"; \
		fi; \
		echo "    copying $$src -> $$dst"; \
		cp -R "$$src" "$$dst"; \
		echo "    installed $$name skill at $$dst"; \
	done; \
	echo "Done. Backups, if any, were moved to ~/.codex/ or ~/.claude/ so agents do not load old and new skills twice."

test: kdebug kbit kentry kloc kberif kcov
	$(MAKE) -C kdebug PYTHON=$(PYTHON) schema-test
	$(MAKE) -C kdebug PYTHON=$(PYTHON) contract-test
	$(MAKE) -C kdebug unit-test
	$(MAKE) -C kdebug PYTHON=$(PYTHON) mcp-test
	$(MAKE) -C kbit PYTHON=$(PYTHON) test
	$(MAKE) -C kentry PYTHON=$(PYTHON) test
	$(MAKE) -C kloc test
	$(MAKE) -C kberif PYTHON=$(PYTHON) test
	$(MAKE) -C kcov PYTHON=$(PYTHON) test
	$(MAKE) sdk-test PYTHON=$(PYTHON)
	$(MAKE) -C kdebug/testdata/combined/active_driver fixture
	regression/run_kdebug_regression.sh

full-test: kdebug kbit kentry kloc kberif
	$(MAKE) -C kbit PYTHON=$(PYTHON) test
	$(MAKE) -C kentry PYTHON=$(PYTHON) test
	$(MAKE) -C kloc test
	$(MAKE) -C kberif PYTHON=$(PYTHON) test
	regression/run_full_regression.sh

clean:
	$(MAKE) -C kdebug clean
	$(MAKE) -C kbit clean
	$(MAKE) -C kentry clean
	$(MAKE) -C kloc clean
	$(MAKE) -C kberif clean
