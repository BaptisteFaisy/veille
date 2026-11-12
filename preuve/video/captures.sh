#!/usr/bin/env bash
# captures.sh — produit les captures RÉELLES de la vidéo Veille.
#
# Les captures sont des sorties de commandes exécutées sur la vraie cible
# QNX 8.0 (émulateur QEMU) : rien n'est rejoué ni re-fabricé à la main.
#
# Prérequis sur le poste hôte :
#   - la VM QNX 8.0 tourne (console série 4444, SSH 8022) ;
#   - /tmp/qnx-ssh existe (wrapper SSH vers root@127.0.0.1:8022) ;
#   - /tmp/qnx-console.py existe (console série TCP 4444).
#
# Variables d'environnement (optionnelles) :
#   QNX_SSH      chemin du wrapper SSH      (défaut : /tmp/qnx-ssh)
#   QNX_CONSOLE  chemin de la console série (défaut : /tmp/qnx-console.py)
#   QNX_PORT     port de la console série   (défaut : 4444)
#   DEST         dossier de sortie          (défaut : <racine>/preuve/video/captures)
#
# Usage : bash preuve/video/captures.sh

set -euo pipefail

RACINE="$(cd "$(dirname "$0")/../.." && pwd)"
DEST="${DEST:-$RACINE/preuve/video/captures}"
QNX_SSH="${QNX_SSH:-/tmp/qnx-ssh}"
QNX_CONSOLE="${QNX_CONSOLE:-/tmp/qnx-console.py}"
QNX_PORT="${QNX_PORT:-4444}"

mkdir -p "$DEST"

if [ ! -x "$QNX_SSH" ]; then
  echo "ERREUR : $QNX_SSH absent ou non exécutable." >&2
  echo "        La VM QNX 8.0 doit tourner ; sinon captures.sh ne peut rien produire." >&2
  exit 2
fi

echo "== captures Veille =="
echo "hôte     : $(uname -srmo)"
echo "invité   : $("$QNX_SSH" 'uname -a' 2>/dev/null | tail -1)"
echo "sortie   : $DEST"
echo

# capture <nom-fichier> <commande-invitée>
# Écrit la commande exacte, l'uname de l'invité, la sortie brute et le code de
# sortie. Un code de sortie non nul n'arrête PAS le script : l'exploration
# exhaustive se termine normalement par un code 1 (contre-exemple trouvé).
capture() {
  local nom="$1" cmd="$2"
  local f="$DEST/$nom" tmp rc=0
  echo "-- $nom : $cmd"
  tmp="$(mktemp)"
  "$QNX_SSH" "$cmd" > "$tmp" 2>&1 || rc=$?
  {
    echo "# commande : $cmd"
    echo "# hôte     : $(uname -srmo)  $(date -Iseconds)"
    echo "# invité   : $("$QNX_SSH" 'uname -a' 2>/dev/null | tail -1)"
    echo "# ---- sortie ----"
    grep -v '^Warning: Permanently added' "$tmp"
    echo "# ---- code de sortie : $rc ----"
  } | tee "$f" > /dev/null
  rm -f "$tmp"
  echo "   -> $f ($(wc -l < "$f") lignes, code de sortie $rc)"
}

# capture_locale <nom-fichier> <commande-hôte>
# Même forme, mais la commande s'exécute sur le poste de travail (comparaison hôte).
capture_locale() {
  local nom="$1" cmd="$2"
  local f="$DEST/$nom" tmp rc=0
  echo "-- $nom (hôte) : $cmd"
  tmp="$(mktemp)"
  eval "$cmd" > "$tmp" 2>&1 || rc=$?
  {
    echo "# commande : $cmd"
    echo "# hôte     : $(uname -srmo)  $(date -Iseconds)"
    echo "# ---- sortie ----"
    cat "$tmp"
    echo "# ---- code de sortie : $rc ----"
  } | tee "$f" > /dev/null
  rm -f "$tmp"
  echo "   -> $f ($(wc -l < "$f") lignes, code de sortie $rc)"
}

# --- 1. La cible : QNX 8.0 réel (pas un mock, pas l'hôte) ------------------
capture "01-cible-uname.txt" 'uname -a; echo; pidin -F "%a %b" | head -3; echo; ls -l /data/veille/veille-sim /data/veille/veille-rm'

# --- 2. Démonstration C sur la cible : le bilan réel ----------------------
capture "02-demo-veille-sim.txt" 'cd /data/veille && ./veille-sim | tail -14'

# --- 3. Exploration exhaustive des 4800 états, sur la cible ---------------
capture "03-exploration-4800-etats.txt" 'cd /data/veille-py && time python3 -m veille.cli proof'

# --- 4. Resource manager /dev/veille : les quatre issues de la chaîne ----
# Redémarrage PROPRE (arrêt par pid, attente du noeud) puis test des quatre
# issues, dans une seule session pour éviter toute course au démarrage.
capture "04-resmgr-4-issues.txt" '
sh /data/veille/rm-restart.sh --no-tick > /tmp/rm-restart.log 2>&1
i=0
while [ ! -e /dev/veille ] && [ $i -lt 20 ]; do sleep 1; i=$((i+1)); done
echo "=== noeud /dev/veille (après $i s) ==="; ls -l /dev/veille
echo
sh /data/veille/rm-test.sh
echo
echo "--- journal serveur (/tmp/rm.log) ---"; tail -5 /tmp/rm.log
echo "--- processus ---"; pidin -F "%p %n" | grep "[v]eille-rm"'

# --- 5. ECG réel (MIT-BIH 222) rejoué DANS la chaîne et écrit dans /dev/veille
capture "05-rejeu-ecg-mitdb-222.txt" 'cd /data/veille-py && time python3 -m veille.resmgr_client --record /data/veille-data/mitdb/222 --signal MLII --sortie /dev/veille'

# --- 6. ECG réel de contrôle (MIT-BIH 100, rythme sinusal normal) ---------
capture "06-rejeu-ecg-mitdb-100.txt" 'cd /data/veille-py && time python3 -m veille.resmgr_client --record /data/veille-data/mitdb/100 --signal MLII --sortie /dev/veille'

# --- 7. Le même bilan sur l'hôte : la chaîne ne se comporte pas autrement ---
capture_locale "07-differentiel-hote-cible.txt" "cd '$RACINE' && make demo 2>&1 | tail -12"

# --- 8. Console série : la cible vue en direct (pas seulement en SSH) ----
if [ -f "$QNX_CONSOLE" ]; then
  echo "-- 08-serial-console.txt : console série (port $QNX_PORT)"
  {
    echo "# commande : python3 $QNX_CONSOLE $QNX_PORT 6 'uname -a' 'pidin -F \"%p %n\" | grep [v]eille-rm'"
    echo "# hôte     : $(uname -srmo)  $(date -Iseconds)"
    echo "# ---- sortie ----"
    python3 "$QNX_CONSOLE" "$QNX_PORT" 6 'uname -a' 'pidin -F "%p %n" | grep [v]eille-rm' 2>&1
  } | grep -v '^Warning: Permanently added' | tee "$DEST/08-serial-console.txt" > /dev/null
  echo "   -> $DEST/08-serial-console.txt ($(wc -l < "$DEST/08-serial-console.txt") lignes)"
else
  echo "!! $QNX_CONSOLE absent : capture console série non produite."
fi

# --- 9. On laisse la VM propre -------------------------------------------
"$QNX_SSH" 'slay -9 veille-rm 2>/dev/null' > /dev/null 2>&1 || true

echo
echo "== captures produites =="
ls -l "$DEST"
