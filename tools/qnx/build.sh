#!/usr/bin/env bash
# Veille — compilation croisée QNX 8.0 du resource manager et des outils de
# mesure (tools/qnx/). Sortie : build/qnx/ (veille-rm, bench_client, hog).
#
#   bash tools/qnx/build.sh              # construit tout
#   QCC_V=gcc_ntoaarch64le bash tools/qnx/build.sh   # cible RPi5
#
# Le SDP 8.0 est requis (qcc) : QNX_SDP=/chemin/vers/sdp par défaut ~/qnx800.
set -euo pipefail
racine=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
cd "$racine"

SDP=${QNX_SDP:-$HOME/qnx800}
QCC_V=${QCC_V:-gcc_ntox86_64}
OUT=${OUT:-build/qnx}
CFLAGS="-std=c11 -O2 -Wall -Wextra -Werror -D_QNX_SOURCE"
INC="-Icore/include -Itarget/pipe -Itarget/port -Itarget/rm"

if [ ! -f "$SDP/qnxsdp-env.sh" ]; then
  echo "[build] SDP introuvable dans $SDP — voir docs/QNX-BUILD.md" >&2
  exit 1
fi
# shellcheck disable=SC1090
. "$SDP/qnxsdp-env.sh" >/dev/null 2>&1

mkdir -p "$OUT"
echo "[build] $(qcc -V 2>&1 | head -1) → $QCC_V"

CORE_SRC=$(ls core/src/*.c)
qcc -V "$QCC_V" $CFLAGS $INC \
  target/rm/rm_chain.c target/rm/rm_io.c target/rm/resmgr_veille.c \
  target/pipe/veille_pipe.c target/port/qnx_time.c $CORE_SRC \
  -o "$OUT/veille-rm"

qcc -V "$QCC_V" $CFLAGS $INC tools/qnx/bench_client.c -o "$OUT/bench_client"
qcc -V "$QCC_V" $CFLAGS $INC tools/qnx/hog.c -o "$OUT/hog"
qcc -V "$QCC_V" $CFLAGS $INC tools/qnx/tick_probe.c -o "$OUT/tick_probe"

file "$OUT/veille-rm" "$OUT/bench_client" "$OUT/hog" "$OUT/tick_probe"
echo "[build] ok → $OUT/"
