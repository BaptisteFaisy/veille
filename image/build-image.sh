#!/bin/sh
# image/build-image.sh — construit l'image invitée QNX 8.0 (IFS) de Veille.
#
# Chaîne : qcc (binaires Veille) → mkifs (IFS) → mkxfs → diskimage.
# Le script ne réimplémente PAS la chaîne : il appelle le paquet réutilisable
# ~/Bureau/qnx-emu (ADOPTER.md), qui porte déjà tous les pièges mkifs/mkxfs.
#
# Usage :
#   sh image/build-image.sh [répertoire_de_travail]
# Variables d'environnement :
#   QNX_SDP   racine du SDP 8.0   (défaut : $HOME/qnx800)
#   QNX_EMU   paquet réutilisable  (défaut : $HOME/Bureau/qnx-emu)
#   VEILLE_SRC racine du dépôt     (défaut : le dépôt de ce script)
set -eu

SDP="${QNX_SDP:-$HOME/qnx800}"
: "${QNX_HOST:=$SDP/host/linux/x86_64}"
: "${QNX_TARGET:=$SDP/target/qnx}"
export QNX_HOST QNX_TARGET

SRC="${VEILLE_SRC:-$(cd "$(dirname "$0")/.." && pwd)}"
WORK="${1:-$HOME/veille-img}"
EMU="${QNX_EMU:-$HOME/Bureau/qnx-emu}"
[ -x "$EMU/build-image.sh" ] || {
    echo "build-image: paquet qnx-emu introuvable ($EMU)" >&2
    echo "  → voir ~/Bureau/qnx-emu/README.md (ADOPTER.md)" >&2
    exit 1
}

# Cœur de Veille (une seule implémentation, partagée sim/RM).
CORE="core/src/alarm.c core/src/chain.c core/src/proof.c core/src/report.c \
core/src/signal.c core/src/signal_gen.c core/src/state.c core/src/verdict.c"

# Includes ABSOLUS : le paquet compile depuis le répertoire de sortie.
CFLAGS="-std=c11 -O2 -D_QNX_SOURCE -I$SRC/core/include -I$SRC/target/pipe \
-I$SRC/target/port -I$SRC/target/rm"

# Groupes « nom: fichiers » séparés par « ; ».
SOURCES="veille-sim:target/sim/sim.c target/pipe/veille_pipe.c target/port/qnx_time.c $CORE"
SOURCES="$SOURCES;veille-rm:target/rm/resmgr_veille.c target/rm/rm_chain.c \
target/rm/rm_io.c target/pipe/veille_pipe.c target/port/qnx_time.c $CORE"
SOURCES="$SOURCES;bench-client:tools/qnx/bench_client.c"

mkdir -p "$WORK"
# Le scénario de démarrage doit être présent dans le répertoire de sortie :
# le buildfile le référence en « ./demo.sh ».
cp "$SRC/image/demo.sh" "$WORK/demo.sh"

cd "$SRC"
"$EMU/build-image.sh" \
    --projet veille \
    --buildfile image/buildfile \
    --sources "$SOURCES" \
    --cflags "$CFLAGS" \
    --sortie "$WORK" \
    --sdp "$SDP" \
    --cible gcc_ntox86_64 \
    "$@"

echo
echo "== dépendances dynamiques des binaires (readelf -d) =="
for b in "$WORK/veille-sim" "$WORK/veille-rm" "$WORK/bench-client"; do
    [ -f "$b" ] || continue
    echo "-- $b"
    readelf -d "$b" | sed -n 's/.*NEEDED.*\[\(.*\)\]/   \1/p'
done
echo
echo "OK : IFS dans $WORK/ifs.bin"
