#!/bin/sh
# capture-trace.sh <label> <prio_client> <duree_s>
# Capture une trace noyau pendant que le resource manager est saturé par un
# client SCHED_FIFO <prio_client> (63 = au-dessus de la priorité 62 du rm).
# À exécuter DANS l'invité QNX (le rm et bench_client doivent y être installés).
# Sortie : /data/trace-<label>.kev (à rapporter sur l'hôte, puis analyser avec
# tools/qnx/trace-e2.py).
LABEL=${1:-trace}
PRIO=${2:-63}
DUR=${3:-10}
cd /data/veille || exit 1
slay -9 veille-rm 2>/dev/null
sleep 1
nohup ./veille-rm > "/tmp/rm-$LABEL.log" 2>&1 &
sleep 1
tracelogger -f "/data/trace-$LABEL.kev" -s "$DUR" > "/tmp/tl-$LABEL.log" 2>&1 &
TL=$!
sleep 1
./bench_client samples --n 200000 --prio "$PRIO" --interval-us 100 --label "$LABEL" \
    > "/tmp/cl-$LABEL.log" 2>&1
wait "$TL" 2>/dev/null
echo "trace : $(ls -l "/data/trace-$LABEL.kev" 2>/dev/null | awk '{print $5}') octets"
echo "client : $(tail -1 "/tmp/cl-$LABEL.log" 2>/dev/null)"
