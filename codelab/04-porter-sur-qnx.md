# Chapitre 4 — Porter sur QNX 8.0

Objectif : faire tourner la chaîne sur une vraie cible QNX 8.0 (QEMU ou Raspberry Pi 5), avec les mécanismes temps réel qui rendent la borne **atteignable**, et le kernel trace qui la **vérifie empiriquement**.

> Ce chapitre est un **guide** : le squelette `target/rm/resmgr_veille.c` est écrit et documenté, mais les essais E2–E4 (priority inheritance observable, cadence stable, disconnect notifié) restent à mener sur une cible réelle. Le socle (chapitres 2–3) est vert sans QNX.

---

## 4.1 Obtenir QNX 8.0 gratuitement

*QNX Everywhere* donne accès à **QNX SDP 8.0**, *QNX Developer Desktop* et *QNX Hypervisor* pour usage **non-commercial**, plus des cours gratuits. Aucune cible matérielle n'est requise : **QEMU** fonctionne, et un **Raspberry Pi 5** aussi.

1. Créez un compte développeur sur le portail QNX et téléchargez SDP 8.0.
2. Installez le toolchain (`qcc`).
3. Pour QEMU : utilisez l'image système fournie par le SDP, ou construisez la vôtre avec `mkifs` (voir §4.6).

Vérifiez le toolchain :

```
qcc -V gcc_ntoaarch64le --version    # pour RPi5 (aarch64le)
qcc -V gcc_ntox86_64 --version       # pour QEMU x86_64
```

## 4.2 Pourquoi un resource manager `/dev/veille`

Décision D5 : un seul processus **possède** la chaîne ; les clients (UI, journal, réseau) y accèdent par API typée (`read`/`write`/`devctl`), jamais par fichier partagé.

```c
/* target/rm/resmgr_veille.c (extrait) */
resmgr_connection_t *conn =
    resmgr_attach(dispatch, &rattr, "/dev/veille", _FTYPE_ANY, 0,
                  NULL, NULL, NULL, &veille_dev.attr);
```

Ce que ça apporte :

- **Isolation** : chaque client a son propre espace d'adresses ; un crash de l'UI ne corrompt pas la chaîne d'alarme.
- **Priority inheritance** : quand un client appelle l'alarme via `MsgSend`, le resource manager tourne à la priorité du client le temps du message.
- **API typée** : `devctl` pour les commandes (lancer la preuve, lire l'état), `read`/`write` pour les données. Pas de protocole maison à sécuriser.

## 4.3 Cadence par pulses et timers noyau (pas de `sleep()`)

L'acquisition doit être **périodique et stable**. Sur un OS généraliste, `sleep(10ms)` dérive selon la charge. Sur QNX, on utilise un timer noyau qui envoie un **pulse** :

```c
/* target/rm/resmgr_veille.c (extrait) */
struct sigevent ev;
SIGEV_PULSE_INIT(&ev, ctp->rcvid, VEILLE_PRIO_CRITICAL, VEILLE_PULSE_TICK, 0);
timer_t tid;
struct itimerspec it = {0};
it.it_value.tv_nsec    = VEILLE_PERIOD_MS * 1000000L;   /* 10 ms */
it.it_interval.tv_nsec = VEILLE_PERIOD_MS * 1000000L;
timer_create(CLOCK_MONOTONIC, &ev, &tid);
timer_settime(tid, 0, &it, NULL);
```

Le pulse arrive dans la boucle de réception avec `rcvid == 0` (message noyau) :

```c
for (;;) {
    ctp = resmgr_context_block(ctp);
    if (ctp->rcvid == 0) {                      /* pulse noyau */
        struct _pulse pulse;
        memcpy(&pulse, ctp, sizeof(pulse));
        if (pulse.code == VEILLE_PULSE_TICK) handle_tick_pulse();
        continue;
    }
    resmgr_handler(ctp, dispatch);              /* read/write/devctl clients */
}
```

La cadence est garantie par le noyau, pas par le scheduler. C'est l'essai **E3** : vérifier que la dérive inter-pulses reste < 1 ms sous charge.

## 4.4 La voie critique : `MsgSend` et priority inheritance

Quand la décision franchit un seuil, l'alarme est déclenchée par un `MsgSend` au sink :

```c
MsgSend(connection_sink, &msg, sizeof(msg), &reply, sizeof(reply));
```

**Ce que fait le noyau QNX :** pendant la durée du message, le sink d'alarme tourne à la **priorité de l'appelant** (`VEILLE_PRIO_CRITICAL = 62`). Même si le sink est un processus de faible priorité en temps normal, il est **temporairement élevé** pour traiter la demande critique. Une tâche best-effort (UI, réseau) ne peut donc **pas** préempter la voie critique.

C'est la différence fondamentale avec un OS généraliste : l'**inversion de priorité** (l'état `prio_inverted` du modèle, +40 ms de pénalité) n'est pas seulement détectée — elle est **corrigée par le noyau**. Sur la cible réelle, la pénalité de 40 ms du modèle devient nulle, et la marge de sûreté augmente.

C'est l'essai **E2** : vérifier que les événements `MsgSend`/`MsgReceive` et les changements de priorité sont visibles dans le kernel trace.

## 4.5 Mort d'un pair : `CHANNEL` disconnect → alarme technique (P2)

Sur un moniteur classique, un capteur mort = **silence** (plus d'échantillon → pas d'alarme). IEC 60601-1-8 exige une **alarme technique**.

Le microkernel QNX notifie la mort d'un pair : quand le sink d'alarme (ou un étage) meurt, le noyau envoie un pulse de **disconnect** sur le canal. Le resource manager le reçoit et déclenche l'alarme technique dans `B_tech` :

```c
/* dans la boucle de réception : pulse disconnect */
/* → alarme technique : la chaîne est rompue, P2 exige B_tech = 50 ms */
```

C'est l'essai **E4** : tuer le sink (`kill -9`), mesurer le délai de notification du disconnect, vérifier que l'alarme technique part dans `B_tech`.

## 4.6 Image système et build cible

Construisez le resource manager pour la cible :

```
qcc -V gcc_ntoaarch64le -O2 -Wall -Wextra -Icore/include \
    target/rm/resmgr_veille.c core/src/*.c -o resmgr_veille
```

Le cœur (`core/`) est **portable** : il compile à l'identique sur hôte et sur cible (c'est tout l'intérêt de la décision D1). Seule la colle QNX (`target/rm/`) est spécifique.

Pour une image système bootable (QEMU), utilisez `mkifs` avec un buildfile qui inclut `procnto`, les drivers nécessaires, et `resmgr_veille` :

```
# image/veilRM.buildfile — squelette à compléter au niveau C
# Structure typique : [on]/[off], sections boot/script/sys, +follow.
# Voir la documentation QNX « Building a Boot Image » pour la syntaxe
# exacte de mkifs et l'ordre des sections.
```

Voir la documentation QNX *Building a Boot Image* pour la structure exacte du buildfile et la commande `mkifs`.

## 4.7 Kernel trace : la preuve empirique

Le kernel trace (`tracelogger`) capture les événements noyau horodatés : `MsgSend`, `MsgReceive`, timers, changements de priorité, interruptions. C'est la **preuve empirique** qui complète la preuve exhaustive du modèle.

Capturez la trace pendant que la chaîne tourne :

```
tracelogger -o trace.kev -b 4M
# ... laisser tourner la chaîne d'alarme, injecter des pannes ...
# Ctrl-C pour arrêter
traceprinter trace.kev > trace.txt
```

Dans `trace.txt`, repérez :

1. le pulse de cadence (`VEILLE_PULSE_TICK`) → `t0` ;
2. le `MsgSend` vers le sink d'alarme → début de la voie critique ;
3. le changement de priorité du sink (héritage à 62) ;
4. la réponse du sink → `t4`.

`L_measured = t4 − t0`. Vérifiez `L_measured ≤ B_proof` (la borne prouvée au chapitre 3). L'écart est la **marge de sûreté** — elle alimente le certificat d'audit.

Visualisez avec le **System Profiler** de QNX Momentics : il affiche les threads, les messages et les priorités sur une frise, ce qui rend la voie critique et l'héritage de priorité visibles à l'œil.

## 4.8 Adaptive partitioning : isoler la partition critique

QNX 8.0 permet de découper le CPU en **partitions** avec des budgets garantis. Placez la chaîne d'alarme dans une partition critique (budget réservé, haute priorité) et l'UI/réseau dans une partition best-effort :

```
# Configuration indicative (à adapter à la cible)
# Partition critique : resmgr_veille + sink d'alarme, budget 30 % garanti
# Partition best-effort : UI, journal, réseau, budget 70 %
```

Même si l'UI s'emballe, la partition critique tient son budget : la charge best-effort ne peut pas retarder l'alarme. C'est la traduction système de l'isolation que le modèle prouve (état `bus_saturated`).

## 4.9 Récapitulatif : la double preuve sur cible

```
┌─────────────────────────────────────────────────────────────┐
│  MODÈLE (chapitre 3)          CIBLE QNX (ce chapitre)        │
│  exploration exhaustive       kernel trace                   │
│  4800 états                   L_measured                     │
│        │                            │                        │
│        ▼                            ▼                        │
│     B_proof  ◄──── vérifie ────  L_measured ≤ B_proof        │
│        │                            │                        │
│        └────────► certificat d'audit IEC 62304 ◄────────────┘
│              (empreinte SHA-256 de la config, horodatage)     │
└─────────────────────────────────────────────────────────────┘
```

- **Preuve exhaustive** (modèle) : la borne est garantie dans les 4800 états de défaillance.
- **Preuve empirique** (trace) : la latence réelle sur cible reste sous la borne prouvée.
- **Certificat** : le rapport Markdown lie les deux à une configuration exacte (empreinte).

C'est cette double preuve qui fait passer l'alarme médicale du statut « elle a sonné en test » à « elle **ne peut pas** être en retard, et voici le certificat qui le prouve ».

## 4.10 Pour aller plus loin

- **Codelab complet** : `codelab/` dans le dépôt (ce que vous lisez).
- **Sûreté de fonctionnement** : `docs/SAFETY.md` (propriétés P1–P3, méthode, limites assumées).
- **Décisions de conception** : `docs/DECISIONS.md` (D1–D12, chacune motivée).
- **Validation des essais** : `docs/VALIDATION.md` (E1–E5, statuts et protocoles).
- **Trous documentés** : `docs/GAP.md` (M1–M6, ce que QNX ne fournit pas).
- **Projets frères** : Ambre (EDR automotive, UN R160), Relais (failover steer-by-wire, UN R79), Tamis (analyse statique des politiques de sécurité).

← [Chapitre 3 : Prouver par exploration exhaustive](03-prouver-par-exploration.md) · [Sommaire](README.md)
