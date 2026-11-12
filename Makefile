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

.PHONY: all test sanitize proof lint clean core host differential sim demo qnx

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
# Pipeline partagé (sim ↔ rm QNX) + couche port horloge (une implémentation par cible)
SIM_SRC  := target/sim/sim.c target/pipe/veille_pipe.c target/port/host_time.c
PORT_INC := -Itarget/pipe -Itarget/port

sim: core
	@mkdir -p build
	$(CC) $(CFLAGS) $(PORT_INC) $(SIM_SRC) $(CORE_OBJ) -o $(SIM_BIN) $(LDFLAGS)

demo: sim
	@echo "=== démo hôte : chaîne capteur→alarme + double preuve ==="
	@./$(SIM_BIN)

# === QNX 8.0 — build LOCAL outillé (SDP requis), volontairement HORS CI :
# les runners GitHub n'ont pas le SDP (recette complète : docs/QNX-BUILD.md).
# qcc pré-définit __QNX__=800 : un -D__QNX__ explicite casserait -Werror (redefined).
# _QNX_SOURCE expose POSIX-2001 (timer_create, CLOCK_MONOTONIC) ET les extensions
# QNX (SIGEV_PULSE_INIT, SETIOV) en -std=c11 strict. qnxsdp-env.sh est bash-only.
QNX_SDP    ?= $(HOME)/qnx800
QCC_V      ?= gcc_ntox86_64        # ou gcc_ntoaarch64le (RPi5) — voir qcc -V
QNX_DIR    ?= build/qnx
QNX_CFLAGS := -std=c11 -O2 -Wall -Wextra -Werror -D_QNX_SOURCE \
              -Icore/include -Itarget/pipe -Itarget/port -Itarget/rm
QNX_CORE_SRC := $(wildcard core/src/*.c)
QNX_SIM_SRC  := target/sim/sim.c target/pipe/veille_pipe.c target/port/qnx_time.c
QNX_RM_SRC   := target/rm/rm_chain.c target/rm/rm_io.c target/rm/resmgr_veille.c \
                target/pipe/veille_pipe.c target/port/qnx_time.c

qnx:
	@bash -c '[ -f $(QNX_SDP)/qnxsdp-env.sh ] || { echo "[qnx] SDP introuvable dans $(QNX_SDP) — voir docs/QNX-BUILD.md"; exit 1; }; \
	  . $(QNX_SDP)/qnxsdp-env.sh >/dev/null; set -e; mkdir -p $(QNX_DIR); \
	  echo "[qnx] $$(qcc -V 2>&1 | head -1) → cible $(QCC_V)"; \
	  qcc -V $(QCC_V) $(QNX_CFLAGS) $(QNX_SIM_SRC) $(QNX_CORE_SRC) -o $(QNX_DIR)/veille-sim; \
	  qcc -V $(QCC_V) $(QNX_CFLAGS) $(QNX_RM_SRC) $(QNX_CORE_SRC) -o $(QNX_DIR)/veille-rm; \
	  file $(QNX_DIR)/veille-sim $(QNX_DIR)/veille-rm'

clean:
	rm -f $(CORE_OBJ) $(CORE_DEP) $(TEST_BIN)
	rm -rf build
	rm -rf host/veille/__pycache__ host/tests/__pycache__ .pytest_cache
	@echo "[clean] fait"
