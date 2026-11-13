#!/bin/sh
# demo.sh — démonstration Veille dans l'invité QNX 8.0 (console VGA).
#
# La vitrine web capture l'écran VGA : tout ce qui est affiché ici est la
# preuve visible. Ordre :
#   1. chaîne complète capteur->alarme, latence MESURÉE sur la cible QNX 8.0 ;
#   2. resource manager /dev/veille (pulses, timers noyau, MsgSend) ;
#   3. client de mesure : aller-retour + moyennes sur /dev/veille ;
#   4. état final : rm relancé, aucune alarme en cours.
#
# CONTRAINTES QNX 8.0 (invité SANS disque) — déjà payées, une par une :
#   - pas de TUBE : ce ksh ne peut pas en créer -> jamais `cmd | autre`,
#     toute filtration passe par un FICHIER ;
#   - pas de substitution de commande `$(...)` : elle utilise un tube ;
#   - pas de `printf` : ni builtin de ce ksh, ni applet dans l'image ->
#     on utilise `echo` ;
#   - le shell de démarrage [+script] ne gère pas $! : c'est ksh qui lance
#     ce fichier (`on -d -t /dev/con1 ... ksh -c /proc/boot/demo.sh`), donc
#     $! est fiable ici.
#
# ASCII : la console VGA de l'invité est orientée OCTET (police CP437) ; un
# octet UTF-8 y serait rendu par deux glyphes illisibles (« dÃ©tectÃ© »).
# On retire donc les octets non ASCII de tout ce qui est affiché (sed), et
# les messages du rm sont écrits en ASCII pur (target/rm/rm_chain.c).
#
# JOURNAL : chaque ligne affichée est aussi copiée dans /dev/shmem/veille-demo.log,
# puis le journal est renvoyé sur la console SÉRIE (cat ... > /dev/ser1) : la
# vitrine web affiche ainsi le scénario complet en texte, en plus de l'écran.

PATH=/proc/boot:/system/bin
LD_LIBRARY_PATH=/proc/boot:/system/lib:/system/lib/dll
export PATH LD_LIBRARY_PATH HOME=/proc/boot

LOG=/dev/shmem/veille-demo.log
SIMOUT=/dev/shmem/veille-sim.out
SIMASC=/dev/shmem/veille-sim.ascii
SIMTAIL=/dev/shmem/veille-sim.tail
OUT=/dev/shmem/veille-cmd.out
OUTA=/dev/shmem/veille-cmd.ascii
: > "$LOG"

# say : écrit sur la console ET dans le journal du scénario.
say() {
    echo "$*"
    echo "$*" >> "$LOG"
}

# show : console seule (la ligne est déjà dans le journal).
show() {
    echo "$*"
}

# ascii : filtre les octets non imprimables (fichier source -> fichier cible).
ascii() {
    sed 's/[^ -~]//g' "$1" > "$2"
}

# run : exécute une commande, affiche sa sortie (ASCII) sur la console, journalise.
run() {
    "$@" > "$OUT" 2>&1
    _rc=$?
    ascii "$OUT" "$OUTA"
    cat "$OUTA"
    cat "$OUTA" >> "$LOG"
    return $_rc
}

# run_tail : journalise TOUTE la sortie, n'affiche que le résumé (dernières lignes).
run_tail() {
    "$@" > "$SIMOUT" 2>&1
    _rc=$?
    ascii "$SIMOUT" "$SIMASC"
    cat "$SIMASC" >> "$LOG"
    tail -n 6 "$SIMOUT" > "$SIMTAIL"
    while read -r _l; do
        show "$_l"
    done < "$SIMTAIL"
    return $_rc
}

say "=== Veille - invite QNX 8.0 : demonstration ==="
say ""
say "[1/4] chaine capteur->alarme : latence mesuree sur la cible QNX 8.0"
run_tail veille-sim
say ""
say "[2/4] resource manager /dev/veille (pulses + timers noyau)"
veille-rm &
RM_PID=$!
sleep 3
say "     /dev/veille en service (pid $RM_PID)"
say ""
say "[3/4] client de mesure : aller-retour + moyennes sur /dev/veille"
run bench-client samples --n 200 --interval-us 2000 --prio 10 --label vitrine
say ""
say "     verdict courant de la chaine :"
run bench-client verdict
say ""
say "     (la deconnexion du client declenche l'alarme technique 'mort d'un pair')"
say ""
say "[4/4] etat final : rm relance, aucune alarme en cours"
slay veille-rm
sleep 2
veille-rm &
RM2_PID=$!
sleep 3
say "     /dev/veille pret (pid $RM2_PID) - invite interactive"
say ""
say "=== fin de la demonstration (l invite reste interactive) ==="

# Le journal du scénario part sur la console série : la vitrine web l'affiche
# en texte (la console VGA, elle, garde la dernière image).
cat "$LOG" > /dev/ser1
