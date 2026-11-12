# Veille — Makefile (socle, sans QNX)
# Tout tourne avec gcc (C11) et python3 (stdlib). Aucune dépendance à installer.

CC      ?= gcc
CFLAGS  ?= -std=c11 -O2 -Wall -Wextra -Werror -Icore/include -MMD -MP
LDFLAGS ?=
PY      ?= python3

CORE_SRC := $(wildcard core/src/*.c)
CORE_OBJ := $(CORE_SRC:.c=.o)
CORE_DEP := $(CORE_OBJ:.o=.d)
TEST_SRC := $(wildcard core/tests/*.c)
TEST_BIN := $(TEST_SRC:.c=.bin)

-include $(CORE_DEP)

.PHONY: all test sanitize proof lint clean core host differential

all: core

core: $(CORE_OBJ)
	@echo "[core] built $(words $(CORE_OBJ)) objects"

%.o: %.c
	$(CC) $(CFLAGS) -c $< -o $@

# Tests C unitaires
core/tests/%.bin: core/tests/%.c $(CORE_OBJ)
	$(CC) $(CFLAGS) $< $(CORE_OBJ) -o $@ $(LDFLAGS)

test: core $(TEST_BIN)
	@echo "=== tests C ==="
	@for t in $(TEST_BIN); do echo "--- $$t ---"; ./$$t || exit 1; done
	@echo "=== tests Python (jumeau) ==="
	@$(PY) -m pytest host/tests -q 2>/dev/null || $(PY) -m unittest discover -s host/tests -q
	@echo "=== différentiel C↔Python ==="
	@$(PY) tests/differential.py
	@echo "[OK] tous les tests verts"

sanitize: CFLAGS += -fsanitize=address,undefined -g
sanitize: clean test

proof: core
	@echo "=== exploration exhaustive (sous-ensemble S4) ==="
	@PYTHONPATH=host $(PY) -m veille.cli proof --subset

lint:
	@echo "=== garde taille fichiers (<500 lignes) ==="
	@fail=0; \
	for f in $(shell find core host target tests -name '*.c' -o -name '*.h' -o -name '*.py' 2>/dev/null); do \
		n=$$(wc -l < $$f); \
		if [ $$n -gt 500 ]; then echo "TROP LONG: $$f ($$n lignes)"; fail=1; fi; \
	done; \
	if [ $$fail -eq 1 ]; then exit 1; fi
	@echo "[OK] tous les fichiers < 500 lignes"

differential: core
	@$(PY) tests/differential.py

SIM_BIN := build/veille-sim

sim: core
	@mkdir -p build
	$(CC) $(CFLAGS) target/sim/sim.c $(CORE_OBJ) -o $(SIM_BIN) $(LDFLAGS)

demo: sim
	@echo "=== démo hôte : chaîne capteur→alarme + double preuve ==="
	@./$(SIM_BIN)

clean:
	rm -f $(CORE_OBJ) $(CORE_DEP) $(TEST_BIN)
	rm -rf build
	rm -rf host/veille/__pycache__ host/tests/__pycache__ .pytest_cache
	@echo "[clean] fait"
