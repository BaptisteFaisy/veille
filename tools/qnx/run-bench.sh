#!/usr/bin/env bash
# Veille — campagne de mesures QNX 8.0 (essais E2/E3/E4 + latences H2).
#
#   bash tools/qnx/run-bench.sh            # toute la campagne (rejouable)
#   bash tools/qnx/run-bench.sh e3         # un seul essai (e2|e3|e4|h2)
#
# Prérequis : VM QNX 8.0 démarrée (voir tools/qnx/boot.sh), binaires croisés
# (tools/qnx/build.sh). Les journaux bruts sont écrits dans preuve/qnx80/ —
# un fichier par mesure, avec la commande, l'uname hôte/invité et la sortie.
#
# Note d'outillage : sur l'invité, un processus lancé en arrière-plan garde le
# canal SSH ouvert (le sshd attend la fin de session) — la commande d'hôte
# ne revient donc pas avant que le processus meure. On lance donc TOUS les
# acteurs d'une mesure dans UNE commande invité, avec les PID capturés pour
# un arrêt propre.
set -euo pipefail

racine=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
cd "$racine"

OUT=${OUT:-preuve/qnx80}
DEST=${DEST:-/data/w5}
SSH_PORT=${SSH_PORT:-8022}
CLE=${CLE:-$HOME/.ssh/qnx-vm_ed25519}
SSH="ssh -p $SSH_PORT -i $CLE -o StrictHostKeyChecking=no \
     -o UserKnownHostsFile=/dev/null -o ConnectTimeout=25 -o BatchMode=yes root@127.0.0.1"
mkdir -p "$OUT"

# --- utilitaires -----------------------------------------------------------
inv() { timeout 90 $SSH "$@"; }                      # commande dans l'invité

journal() {                                          # journal <etiquette> <cmd>
  local etq="$1" cmd="$2" ts
  ts=$(date -u +%Y%m%dT%H%M%SZ)
  local f="$OUT/${etq}-${ts}.log"
  {
    echo "# commande : $cmd"
    echo "# hôte     : $(uname -srmo)  $(date -Iseconds)"
    echo "# invité   : $(inv 'uname -a' 2>/dev/null | tail -1)"
    echo "# ---- sortie ----"
    set +e
    inv "$cmd" 2>&1
    local rc=$?
    set -e
    echo "# ---- code de sortie : $rc ----"
  } | tee "$f"
  echo "[bench] journal → $f"
}

rm_start() {                                         # rm_start "<options>"
  inv "cd $DEST && slay -9 veille-rm 2>/dev/null; sleep 1; \
       nohup ./veille-rm $1 </dev/null > /tmp/rm-w5.log 2>&1 & sleep 2" >/dev/null 2>&1 || true
}

rm_stop()  { inv "slay -9 veille-rm 2>/dev/null" >/dev/null 2>&1 || true; }

# Acteurs d'une mesure : hog (charge CPU SCHED_FIFO 30) et/ou flood (client
# qui inonde le rm), puis la sonde. Tout dans UNE commande invité.
scene() {                                            # scene <charge: hog|flood|hog+flood> <sonde>
  local charge="$1" sonde="$2"
  {
    echo "cd $DEST"
    case "$charge" in
      hog*|flood*)
        echo "./hog --prio 30 --hold-ms 20 --sleep-ms 1 --duration-ms 60000 > /tmp/hog.log 2>&1 & HOG=\$!" ;;
    esac
    case "$charge" in
      flood*|hog*)
        echo "./bench_client samples --n 1000000 --prio 5 --interval-us 0 --label flood > /tmp/flood.log 2>&1 & FL=\$!" ;;
    esac
    echo "sleep 1"
    echo "$sonde"
    echo "kill \$HOG \$FL 2>/dev/null; true"
  }
}

# --- E3 : cadence réelle du tick (au repos puis sous charge) ---------------
e3() {
  echo "=== E3 : cadence du tick noyau (10 ms) ==="
  rm_stop
  rm_start "--watchdog-ms 0"                          # tick actif, watchdog coupé
  echo "[bench] E3 repos — 20 s de ticks au repos…"
  inv "sleep 20" >/dev/null 2>&1 || true
  journal "e3-tick-repos" "cd $DEST && ./bench_client stats"

  echo "[bench] E3 sous charge — un client inonde le rm pendant 20 s…"
  journal "e3-tick-charge" "$(scene flood 'sleep 20; ./bench_client stats')"
  rm_stop
  # contrôle indépendant : sonde sur SON PROPRE canal (perte de pulses noyau
  # ou traitement du rm ? — même timer, même période, aucun rm involved)
  journal "e3-sonde-independante" "cd $DEST && ./tick_probe --period-ms 10 --duration-ms 20000"
}

# --- E4 : watchdog « capteur muet » ----------------------------------------
e4() {
  echo "=== E4 : watchdog capteur muet (seuil 1000 ms, --no-tick) ==="
  rm_stop
  rm_start "--no-tick --watchdog-ms 1000"
  echo "[bench] E4 — aucun échantillon pendant 3 s → alarme attendue…"
  inv "sleep 3" >/dev/null 2>&1 || true
  journal "e4-capteur-muet" "cd $DEST && ./bench_client verdict"
  echo "[bench] E4 — un client écrit des échantillons → l'alarme doit se lever…"
  journal "e4-retour-signal" "cd $DEST && ./bench_client hold --silence-ms 3000 --duration-ms 2000 --interval-us 200000 --bpm 72"
  journal "e4-stats" "cd $DEST && ./bench_client stats"
  rm_stop
}

# --- latences H2 : échantillon → verdict (au repos puis sous charge) -------
h2() {
  echo "=== H2 : latence échantillon → verdict ==="
  rm_stop
  rm_start "--watchdog-ms 0"
  echo "[bench] H2 repos — 1000 échantillons à ~2 ms…"
  journal "h2-repos" "cd $DEST && ./bench_client samples --n 1000 --interval-us 2000 --bpm 72 --stats --label repos"
  echo "[bench] H2 sous charge — client inondeur en parallèle…"
  journal "h2-charge" "$(scene flood './bench_client samples --n 1000 --interval-us 2000 --bpm 72 --stats --label charge')"
  rm_stop
}

# --- E2 : héritage de priorité, mesuré par le comportement ----------------
e2() {
  echo "=== E2 : héritage de priorité (SCHED_FIFO, comportement) ==="
  e2_run() {   # e2_run <étiquette> <options-rm> <prio-sonde> <charge>
    local etq="$1" rmopts="$2" p="$3" charge="$4"
    echo "[bench] $etq (rm $rmopts ; sonde prio $p ; charge $charge)"
    rm_stop
    rm_start "$rmopts"
    journal "$etq" "$(scene "$charge" "./bench_client samples --n 300 --prio $p --interval-us 5000 --bpm 72 --label $etq; echo '--- charge active ---'; pidin -F '%p %n' 2>/dev/null | grep -Ei 'hog|bench_client' | head -5")"
    journal "${etq}-stats" "cd $DEST && ./bench_client stats"
  }

  # Régime 1 — rm SATURÉ (file d'attente FIFO) : le client attend son tour.
  e2_run "e2-a-sature-inherit"      "--prio 10 --watchdog-ms 0" 40 "hog+flood"
  e2_run "e2-b-sature-noinherit"    "--prio 10 --watchdog-ms 0 --no-inherit" 40 "hog+flood"
  e2_run "e2-c-sature-sonde-basse"  "--prio 10 --watchdog-ms 0" 20 "hog+flood"
  e2_run "e2-d-sature-production"   "--prio 62 --watchdog-ms 0" 40 "hog+flood"
  # Régime 2 — rm au REPOS (il attend dans dispatch_block) : c'est là que le
  # boost d'héritage peut faire gagner du temps au client prioritaire.
  e2_run "e2-e-repos-inherit"       "--prio 10 --watchdog-ms 0" 40 "hog"
  e2_run "e2-f-repos-noinherit"     "--prio 10 --watchdog-ms 0 --no-inherit" 40 "hog"
  e2_run "e2-g-repos-production"    "--prio 62 --watchdog-ms 0" 40 "hog"
  rm_stop
}

case "${1:-all}" in
  e2) e2 ;;
  e3) e3 ;;
  e4) e4 ;;
  h2) h2 ;;
  all|*) e3; e4; h2; e2 ;;
esac
echo "[bench] fin — journaux dans $OUT/"
