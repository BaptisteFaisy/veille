#!/bin/sh
# demo.sh — la démonstration Veille, en phases lisibles sur l'écran de l'invité.
#
# L'écran VGA de l'invité fait 80x25 : une démo qui défile n'est pas une démo
# visible. On joue donc QUATRE phases, chacune tenant dans l'écran (≤ 20
# lignes), séparées par une pause : à chaque instant, l'écran de l'émulateur
# montre une phase complète et lisible. Les phases rebouclent trois fois, puis
# l'invite interactive reste en place.
#
# Phases :
#   1. preuve     — exploration exhaustive : 4 800 états, borne 200 ms
#   2. simulation — 600 échantillons, pannes injectées, alarmes bornées
#   3. signal     — les 4 états capteur (figé / tachy / mort / régulier)
#   4. cible      — resource manager /dev/veille + client de mesure + verdict
#
# CONTRAINTES QNX 8.0 (invité SANS disque) — déjà payées :
#   - pas de TUBE : ce ksh ne peut pas en créer -> jamais `cmd | autre` ;
#   - pas de substitution de commande `$(...)` : elle utilise un tube ;
#   - pas de `printf` : ni builtin de ce ksh, ni applet dans l'image -> `echo` ;
#   - la console VGA est orientée OCTET (police CP437) : tout ce qui est
#     affiché est en ASCII (les messages du rm aussi, voir target/rm/rm_chain.c).
#
# JOURNAL : chaque phase est aussi copiée dans /dev/shmem/veille-demo.log, et le
# journal complet part sur la console SÉRIE (cat ... > /dev/ser1) pour que la
# vitrine HTTP l'affiche en texte à côté de l'écran.

PATH=/proc/boot:/system/bin
LD_LIBRARY_PATH=/proc/boot:/system/lib:/system/lib/dll
export PATH LD_LIBRARY_PATH HOME=/proc/boot

LOG=/dev/shmem/veille-demo.log
SIMOUT=/dev/shmem/veille-sim.out
SELOUT=/dev/shmem/veille-sel.out
OUT=/dev/shmem/veille-cmd.out
RMOUT=/dev/shmem/veille-rm.out
: > "$LOG"

# say : console VGA + journal du scenario + console serie.
# La serie est ecrite ligne a ligne : sans cela, la vitrine HTTP n'affiche le
# scenario qu'a la fin (le journal etant renvoye d'un seul bloc en fin de
# demonstration).
say() {
    echo "$*"
    echo "$*" >> "$LOG"
    echo "$*" > /dev/ser1
}

# show : console seule (le texte est déjà dans le journal).
show() {
    echo "$*"
}

# pick : extrait d'un fichier les lignes qui contiennent un motif, vers un
# fichier (jamais de tube sur QNX 8.0 sans disque).
#
# Les sorties du simulateur sont en UTF-8 (accents) alors que la console VGA
# est orientee OCTET (CP437) : un accent UTF-8 y devient deux glyphes
# illisibles (« provedA© »). On retire donc les octets non ASCII de tout ce
# qui est affiche — c'est aussi pour cela que les messages du rm sont en ASCII.
# pick <motif> <fichier> [expression sed]
# Extrait les lignes qui contiennent le motif, les met en ASCII (console
# orientee octet), les compacte (espaces multiples -> un espace), eventuellement
# reformatees par l'expression sed, puis les coupe a 76 colonnes : l'ecran VGA
# fait 80 colonnes, au-dela la ligne se replie et devient illegible.
pick() {
    grep "$1" "$2" > "$SELOUT.raw" 2>/dev/null
    if [ "$#" -ge 3 ]; then
        sed -e 's/[^ -~]//g' -e "$3" -e 's/   */ /g' "$SELOUT.raw" > "$SELOUT.asc"
    else
        sed -e 's/[^ -~]//g' -e 's/   */ /g' "$SELOUT.raw" > "$SELOUT.asc"
    fi
    cut -c 1-76 "$SELOUT.asc" > "$SELOUT"
    cat "$SELOUT"
    cat "$SELOUT" > /dev/ser1
}

# phase : vide l'ecran puis affiche le titre, pour qu'une seule phase soit
# visible a la fois. La sequance d'echappement est litterale (octet 0x1B) :
# l'image n'a ni `printf` ni `clear`, et on ne depend pas de l'interpretation
# des anti-slashes par `echo`.
phase() {
    echo "[2J[H"
    say "================================================================"
    say "  $1"
    say "================================================================"
}

pause() {
    sleep "$1"
}

# ---------------------------------------------------------------- 1. la preuve
phase_preuve() {
    phase "PHASE 1/4  PREUVE  -  exploration exhaustive des etats"
    say "  Borne d'alarme prouvee (B_proof)      : 200 ms"
    say "  Etats explores dans l'invite QNX 8.0   :"

    pick "VEILLE_PROOF_COMPLETE" "$SIMOUT"
    say ""
    say "  La garantie tient sur TOUS les etats, pas sur un echantillon."
    pause 6
}

# ------------------------------------------------------------- 2. la simulation
phase_simulation() {
    phase "PHASE 2/4  SIMULATION  -  600 echantillons, pannes injectees"
    pick "alarmes physiologiques" "$SIMOUT"
    pick "alarmes techniques" "$SIMOUT"
    pick "marge de" "$SIMOUT"
    pick "L_measured" "$SIMOUT"
    say ""
    say "  Latence MESUREE dans l'invite, comparee a la borne prouvee."
    pause 6
}

# ------------------------------------------------------------- 3. le signal brut
phase_signal() {
    phase "PHASE 3/4  SIGNAL BRUT  -  les 4 etats capteur"
    pick "capteur=" "$SIMOUT" 's/capteur=sensor_//'
    say ""
    say "  Capteur fige detecte sur le SIGNAL BRUT (pas sur le bpm)."
    say "  Tachycardie = alarme physiologique, pas fausse alarme technique."
    pause 6
}

# ---------------------------------------------------------------- 4. la cible
phase_cible() {
    phase "PHASE 4/4  CIBLE  -  resource manager /dev/veille + mesure"
    say "  /dev/veille en service (resource manager QNX, SCHED_FIFO 62)"
    bench-client samples --n 200 --interval-us 2000 --prio 10 --label vitrine \
        > "$OUT" 2>&1
    pick "fin label" "$OUT"
    pick "VEILLE_" "$OUT" 's/^\(....\)[ ]*VEILLE_\([A-Z_]*\).*bound=\([0-9]*\).*/\1 VEILLE_\2  borne=\3 ms/'
    say ""
    say "  Verdict de la chaine apres la deconnexion du client :"
    bench-client verdict > "$OUT" 2>&1
    pick "VEILLE_" "$OUT" 's/^\(....\)[ ]*VEILLE_\([A-Z_]*\).*bound=\([0-9]*\).*/\1 VEILLE_\2  borne=\3 ms/'
    say ""
    say "  Alarme technique 'mort d'un pair' declenchee a la deconnexion."
    pause 6
}

# ------------------------------------------------------------------- le scenario
say "=== Veille - invite QNX 8.0 : demonstration complete ==="
say "    (4 phases lisibles, l'ecran VGA fait 80x25)"

# 1) La simulation complete est jouee UNE fois ; les phases relisent le
#    resultat dans le fichier (pas de tube, pas de substitution de commande).
say ""
say "  [preparation] veille-sim : preuve + simulation + signaux bruts..."
veille-sim > "$SIMOUT" 2>&1
say "  [preparation] termine."

# 2) Le resource manager, une fois pour toute la demonstration.
veille-rm > "$RMOUT" 2>&1 &
RM_PID=$!
sleep 2
say "  [preparation] /dev/veille en service (pid $RM_PID)"

# 3) Les phases, en boucle : trois tours, puis l'invite interactive.
CYCLE=1
while [ "$CYCLE" -le 3 ]; do
    say ""
    say "---------------- cycle $CYCLE / 3 ----------------"
    phase_preuve
    phase_simulation
    phase_signal
    phase_cible
    CYCLE=$((CYCLE + 1))
done

say ""
say "=== demonstration terminee : l'invite reste interactive ==="
say "    (les commandes tapes ici vont a l'invite QNX 8.0)"

# Le journal du scenario part sur la console serie : la vitrine web l'affiche
# en texte (la console VGA, elle, garde la derniere image).
cat "$LOG" > /dev/ser1
