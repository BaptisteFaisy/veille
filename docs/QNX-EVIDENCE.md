# Veille — preuve sur cible QNX 8.0

Ce document est le **compte rendu factuel** de ce qui a été exécuté sur une vraie
cible QNX 8.0 (émulateur QEMU), et de ce qui ne l'a pas été. Les journaux bruts
sont dans [`preuve/qnx80/`](../preuve/qnx80/) — un fichier par exécution, avec la
commande, l'`uname` de l'hôte et de l'invité, la sortie et le code de sortie.

Date : 12 novembre 2026. Auteur : b (agent, lot « preuves QNX manquantes »).

**Résumé honnête** : les essais **E2** (héritage de priorité), **E3** (cadence
du timer) et **E4** (silence du capteur) sont désormais **mesurés sur la
cible réelle**, avec leurs journaux. E2 est **observé mais partiellement
quantifié** (le mécanisme est prouvé, l'effet n'est visible que dans la
queue de latence). E3 est **mesuré et défavorable** sur cette cible
virtualisée : la cadence à 10 ms n'est pas tenue à 100 Hz. E4 est **démontré**
(alarme technique « capteur muet »). Les latences réelles sous charge sont
**mesurées** et **tenent** la borne de 200 ms au p99, mais pas au maximum.
Une **trace noyau de 10 s** a été capturée et décodée pendant qu'un client
SCHED_FIFO 63 saturait le rm : elle montre le chemin de message passing de la
voie critique, mais cette image n'expose aucun événement de changement de
priorité — la trace **ne prouve donc pas** l'héritage (§5.1 bis).

---

## 1. Environnement de la cible

| Élément | Valeur |
|---|---|
| Système invité | `QNX qnxqemu 8.0.0 2026/06/05-16:26:03EDT x86pc x86_64` |
| Image | QNX Everywhere Quick Start Target Image (QEMU), `qnx_sdp8.0_qemu_quickstart_20260902` |
| Émulation | QEMU 8.2.2, KVM activé, 3 Gio de RAM, 4 vCPU |
| Compilateur | SDP 8.0 (QNX Software Center), `qcc` = GCC **12.2.0**, cible `gcc_ntox86_64` |
| Accès | SSH root par clé (port 8022), console série TCP (port 4444) |
| Chaîne porteuse | `core/` (C11 pur) + `host/` (jumeau Python) + `target/` (resmgr, sim, pipe) |

Recette de mise en route (hôte Linux) — **scriptée et rejouable** :

```bash
bash tools/qnx/boot.sh --start     # démarre la VM et attend le SSH
bash tools/qnx/boot.sh --status    # état
bash tools/qnx/boot.sh --stop      # arrêt propre (PID file)
```

Le script `tools/qnx/boot.sh` encapsule la commande QEMU exacte (mêmes options
à chaque fois : 4 vCPU, 3 Gio, KVM, port SSH 8022, console série 4444, disque
`output/disk-qemu.vmdk`, image `output/ifs.bin`) et n'arrête que la VM qu'il a
lancée (PID file `output/qemu.pid`).

## 2. Compilation croisée

Deux chemins, tous deux vérifiés :

* `make qnx` (Makefile du dépôt, SDP 8.0) → `build/qnx/veille-rm`,
  `build/qnx/veille-sim`.
* `bash tools/qnx/build.sh` (outillage de preuve) → **en plus** les outils de
  mesure : `bench_client`, `hog`, `tick_probe`.

Écarts assumés (détaillés dans [`QNX-BUILD.md`](QNX-BUILD.md)) : pas de `-D__QNX__`
(qcc le pré-définit à `800`, un `-D__QNX__` nu casse `-Werror`), `-D_QNX_SOURCE`
pour `timer_create`/`CLOCK_MONOTONIC` et les extensions QNX (pulses).

## 3. Exécutions réelles sur la cible

### 3.1 Démonstration C (`veille-sim`) — même bilan que sur l'hôte

```
alarmes physiologiques : 291 (latence max 0.001 ms, borne prouvée 200 ms)
alarmes techniques     : 8 (latence max 0.000 ms, borne 50 ms)
marge de sûreté        : 200 ms (borne prouvée - latence mesurée max)
[OK] L_measured <= B_proof sur tous les échantillons — double preuve cohérente.
```

Identique à la sortie hôte : la chaîne C se comporte de même sous QNX 8.0.
Journal : `preuve/qnx80/preuve-cible-synth-*.log`.

### 3.2 Exploration exhaustive des 4800 états — sur la cible

Le jumeau Python (Python **3.14** dans l'image) parcourt les 4800 états de
défaillance **sur QNX** :

```
ERROR  VEILLE_PROOF_COUNTEREXAMPLE  bound=100ms  latency=105ms  states=4800
FAILED 1 error(s)
real 0m0.126s
```

Même verdict et même temps que sur l'hôte (`(4800, 105)`), en deux ordres de
grandeur de temps Machine.

### 3.3 Resource manager `/dev/veille` — les quatre issues de la chaîne

Écritures réelles dans le nœud, lectures du verdict au format texte du contrat :

| Cas | Écriture | Verdict sur cible |
|---|---|---|
| Rythme normal | 8 échantillons ~72 bpm | `INFO VEILLE_OK … alarm_none bound=200` |
| Tachycardie soutenue | 8 échantillons à 132 bpm | `INFO VEILLE_OK … alarm_single bound=200` (alarme haute déclenchée) |
| Capteur figé | même valeur répétée | `WARN VEILLE_TECHNICAL_ALARM … sensor_stuck … bound=50` |
| Capteur mort | valeur négative | `WARN VEILLE_TECHNICAL_ALARM … sensor_dead … bound=50` |
| Retour normal | 8 échantillons ~72 bpm | `INFO VEILLE_OK … alarm_none bound=200` |

Journal : `preuve/qnx80/preuve-resmgr-cible-*.log`.

### 3.4 Données réelles (PhysioNet) rejouées **dans** l'émulateur

| Jeu | Enregistrement | Signal | Résultat sur cible |
|---|---|---|---|
| MIT-BIH Arrhythmia | 100 | ECG MLII, 360 Hz | `INFO VEILLE_OK chain=100_MLII latency=50ms` (rythme sinusal normal : aucune alarme, conforme) |
| MIT-BIH Arrhythmia | 105 | ECG MLII | `INFO VEILLE_OK chain=105_MLII latency=50ms` |
| MIT-BIH Arrhythmia | 222 | ECG MLII (fibrillation atriale) | 2500 pics R détectés, 2401 échantillons de bpm réels écrits dans `/dev/veille` (bpm 43 → 182, moyenne 87,9) |
| MIT-BIH Arrhythmia | 205 | ECG MLII (tachycardie ventriculaire) | 2647 pics R, bpm 46 → 200 |
| BIDMC | bidmc01 | ECG + PLETH + SpO2 | SpO2 réel lu 96–98 %, HR 88–95 bpm |
| MIT-BIH Polysomnographic | slp02a | ECG + pression artérielle | PA réelle : 41 → 109,47 mmHg |

Le rapport d'audit produit **sur la cible** porte l'empreinte du fichier source :

```
- Configuration : /data/veille-data/mitdb/105
- Empreinte SHA-256 : fcd0153dfea69c749194bb73de7db124588857cfa2f6aecb72754894c8afde02
- Horodatage (UTC) : 2026-11-12T14:45:18Z
```

Journaux : `preuve/qnx80/preuve-replay-mitdb*-*.log`,
`preuve/qnx80/preuve-reel-*-*.log`, `preuve/qnx80/preuve-vt205-cible-*.log`.

## 4. Défauts trouvés en passant sur la vraie cible (corrigés)

1. **`io_write` retournait le nombre d'octets comme code d'erreur.** Le handler
   terminait par `return _IO_SET_WRITE_NBYTES(ctp, nb);` — cette macro *pose* le
   statut dans `ctp` et **retourne sa valeur** (le nombre d'octets). Le client
   recevait donc `EINVAL`-like : `E2BIG` pour 7 octets, `ENOEXEC` pour 8, `ENXIO`
   pour 6 — c'est-à-dire un errno déduit de la taille de l'écriture. Le pattern
   officiel du SDP (`s1_resmgr_write_simple`) impose `_IO_SET_WRITE_NBYTES(ctp, n)`
   puis `return EOK`.
2. **Lecture des données par copie contiguë.** `memcpy(buf, (const char *)(msg+1), nb)`
   suppose les données collées à l'en-tête `io_write_t` ; le SDP impose
   `resmgr_msgget(ctp, buf, nb, sizeof(msg->i))`.
3. **Une seule valeur par écriture.** Un client qui écrit en tampon (Python :
   buffer de 8 Ko) envoie plusieurs lignes d'un coup → `EINVAL`. Le serveur
   accepte désormais jusqu'à 256 échantillons par écriture (une ligne invalide
   rejette l'écriture entière : aucune moitié n'est poussée).
4. **`O_CREAT` sur un périphérique.** `os.open('/dev/veille', O_WRONLY|O_CREAT)`
   renvoie `EINVAL` : le resource manager refuse la création. Le client ouvre
   désormais en écriture seule si le chemin existe, et en mode ligne par ligne
   (un échantillon par `write()`), ce qui préserve la cadence réelle.
5. **Notification de disconnect parasite.** La notification `_PULSE_CODE_DISCONNECT`
   arrivait sans client connecté et empoisonnait le verdict courant. Le serveur
   compte désormais les clients (handler `open`) et n'alerte que si un client
   était réellement connecté.
6. **`MSG_FLAG_ALLOC_PULSE` désynchronisait le timer et le handler de pulse.**
   `pulse_attach(dpp, MSG_FLAG_ALLOC_PULSE, code, …)` **ignore le code demandé**
   et fait allouer par le dispatch un code arbitraire ; le timer, lui, envoie
   toujours au code écrit dans `SIGEV_PULSE_INIT`. Résultat : **le tick de 10 ms
   n'était jamais servi** (le handler de pulse était ailleurs). Le tick n'a
   fonctionné qu'après correction (`pulse_attach(dpp, 0, code, …)` sans le
   drapeau ALLOC). C'est un défaut **majeur et silencieux** : le rm « vivait »,
   le tick ne partait pas, et rien ne le signalait. Constaté par un compteur de
   ticks ajouté au rm (§5.2).
7. **Le pulse de cadence partait sur un canal latéral non servi.** Avec
   `message_connect(dpp, MSG_FLAG_SIDE_CHANNEL)`, les pulses allaient sur le
   canal latéral, que `dispatch_block()` ne sert pas : le tick n'était jamais
   reçu. Le coid est maintenant pris sur le canal principal
   (`message_connect(dpp, 0)`).
8. **Une alarme technique masquait le verdict du capteur.** Le rapport ne
   portait qu'un seul verdict : une mort de pair effaçait l'alarme « capteur
   muet » (et inversement). Le rm tient désormais l'alarme technique **à part**
   (`VEILLE_TECH_*`) et le rapport porte les deux verdicts (le format du CONTRAT
   accepte plusieurs verdicts).

## 5. Essais E2 / E3 / E4 — ce qui est mesuré sur la cible

Outillage de mesure : `tools/qnx/` (voir `tools/qnx/README.md`). Rejeu
complet en une commande :

```bash
bash tools/qnx/build.sh          # compilation croisée (qcc)
bash tools/qnx/run-bench.sh all  # toute la campagne → preuve/qnx80/
python3 tools/qnx/analyse.py preuve/qnx80   # tableaux de chiffres
```

Deux canaux de mesure ont été ajoutés au resource manager (tous deux
**hors du format du CONTRAT**, qui n'est pas touché) :

* un **compteur de ticks** et des **statistiques d'intervalle** dans le rm
  (E3) ;
* un **historique des priorités effectives** vues par le rm à la réception
  des messages clients (E2), et la **latence de chaîne** mesurée côté serveur
  (H2).

Ils sont rendus au format **texte `cle=valeur`** par un `read()` à un offset
réservé (`VEILLE_STATS_OFFSET`), lisible directement dans les journaux.

### 5.1 E2 — héritage de priorité : **observé, effet partiel et conditionnel**

**Question.** Quand un client prioritaire envoie un `MsgSend` au rm, le noyau
lui accorde-t-il sa priorité, et le client en profite-t-il ?

**Méthode (comportementale, sans trace noyau).** Le rm lit sa **propre
priorité effective** au moment où il reçoit le message
(`pthread_getschedparam`) et la range dans un histogramme
(`prio_hist[priorité]`). Un client de sonde à priorité SCHED_FIFO connue
(40) écrit 300 échantillons dans `/dev/veille` et mesure l'**aller-retour**
(horodatage `CLOCK_MONOTONIC` de part et d'autre du `write()`). Charge
concomitante : un *hog* SCHED_FIFO 30 (20 ms d'occupation / 1 ms de repos) et,
selon l'essai, un client qui inonde le rm. **Contrôle négatif** : l'option
`--no-inherit` fait rendre explicitement au rm sa priorité de base en début
de traitement ; la priorité est relue après l'annulation pour vérifier que le
témoin est valide (`prio_after_drop`).

**Résultats bruts** (300 échantillons par essai, µs) :

| essai | régime | rm | sonde | p50 | p95 | p99 | max | priorité vue par le rm |
|---|---|---|---|---|---|---|---|---|
| A | saturé | 10 | 40 | 32 | **69** | **1 939** | 5 037 | 40 (×300) |
| B | saturé | 10 | 40 | 34 | **5 634** | **12 879** | 29 885 | 40 (×300) |
| C | saturé | 10 | 20 | 34 | 3 823 | 10 408 | 90 086 | 20 (×300) |
| D | saturé | 62 | 40 | 30 | 3 926 | 12 831 | 32 955 | 40 (×300) |
| E | au repos | 10 | 40 | 34 | 5 100 | 16 544 | 36 331 | 40 (×300) |
| F | au repos | 10 | 40 | 39 | 6 993 | 13 547 | 52 360 | 40 (×300) |
| G | au repos | 62 | 40 | 24 | 5 029 | 17 051 | 33 279 | 40 (×300) |

* A = héritage actif, B = **héritage annulé** (même rm, même charge, même
  sonde : seul le boost diffère ; `prio_after_drop = 10` confirme que
  l'annulation a bien pris effet).
* C : sonde **sous** le hog (20 < 30). D/G : rm à sa priorité de production
  (62).

**Conclusions, sans enjoliver.**

1. **Le mécanisme est observé.** À la réception des messages du client
   prioritaire, le rm s'exécute **à la priorité du client** (40, ou 20 dans
   l'essai C) — y compris quand sa propre base est 10 **ou** 62. L'héritage
   de priorité du noyau est donc bien actif et **mesurable par le
   comportement** (300 messages par essai, 0 exception).
2. **L'effet sur l'attente du client est réel mais ne porte que sur la
   queue.** En régime **saturé** (A vs B), le p50 est identique (32 vs 34 µs)
   mais le **p95 est 82× plus élevé sans héritage** (69 vs 5 634 µs) et le
   **p99 6,6× plus élevé** (1 939 vs 12 879 µs). L'héritage ne rend pas le
   cas typique plus rapide : il **empêche le client d'être affamé** quand le
   rm est chargé.
3. **En régime au repos (E vs F), aucune différence mesurable** (p95 5 100 vs
   6 993 µs, p99 16 544 vs 13 547 µs — dans le bruit de la charge). Le boost
   d'héritage ne se manifeste que lorsque le rm a du travail en attente.
4. **Limite importante et contre-intuitive.** La priorité de base du rm
   (62, « voie critique ») **ne le protège pas** : pendant le service d'un
   client de priorité 5, le rm s'exécute à 5 (`prio_hist` des essais D et G :
   `5×134 502` puis `40×300`). QNX 8.0 aligne la priorité du **receveur** sur
   celle de l'**émetteur** pendant le `MsgSend` : un client de faible
   priorité peut donc **déprioriser** le rm. Pour une voie critique réelle,
   il faut un fil de service dédié (priorité fixe) et non un dispatch
   monolithique.
5. **E2 n'est donc pas « vérifié » au sens fort** : l'héritage est *observé*
   et son effet est *quantifié dans un régime particulier*. La garantie
   « le client prioritaire n'attend jamais plus de X » **n'est pas** établie
   par ces mesures : au maximum observé, l'attente atteint **90 ms** (essai C,
   sonde sous le hog).

### 5.1 bis — E2 par kernel trace : **la trace est capturée et décodée, mais l'événement de changement de priorité n'est pas exposé**

**Ce qui a été fait.** `tracelogger` (dans l'image QNX 8.0) capture 10 s de
noyau pendant que le rm tourne avec son tick et qu'un client SCHED_FIFO **63**
— donc *au-dessus* de la priorité 62 du rm — inonde `/dev/veille`. La trace est
ramenée sur l'hôte et décodée par le `traceprinter` du SDP. **Commande à
retenir : `traceprinter -f fichier.kev`** — l'argument positionnel est *ignoré*
(l'outil va alors lire `/dev/shmem/tracebuffer.kev` et échoue avec « internal
error code(12) », ce qui avait fait croire à un format de trace incompatible).

Deux captures comparables (10 s chacune) :

| Mesure tirée de la trace noyau | client SCHED_FIFO 63 | client SCHED_FIFO 10 |
|---|---|---|
| événements de la classe COMM attachés au pid du rm | **13 865** | 2 991 |
| états THREAD du rm — THRUNNING | 7 340 | 2 144 |
| états THREAD du rm — THRECEIVE | 6 081 | 997 |
| lignes décodées | 1 588 768 | 2 949 255 |

**Ce que la trace montre** : le chemin de message passing de la voie critique
est bien dans le noyau, et le rm servie par un client plus prioritaire **tourne
et répond** (6 081 réceptions, 1 040 réponses, 13 865 événements de
communication rattachés au rm) pendant que ce client la sature.

**Ce que la trace ne montre pas** : cette image n'expose **aucun événement de
changement de priorité** (classes disponibles : THREAD, KER_CALL, KER_EXIT,
SYSTEM, COMM, INTERRUPT, CONTROL, PROCESS). La trace **ne prouve donc pas**
l'héritage de priorité : la preuve reste la mesure comportementale A/B
ci-dessus (p95 82× plus élevé sans héritage). Journaux :
`preuve/qnx80/e2-trace-kernel-*.txt`, empreintes des `.kev` dans
`e2-trace-kernel.sha256`, extrait de 40 lignes de trace dans
`e2-trace-kernel-extrait.txt`. Outillage : `tools/qnx/trace-e2.py`.

### 5.2 E3 — cadence du timer : **mesurée, et non tenue à 100 Hz sur cette cible**

**Question.** Le rm cadence l'acquisition avec `timer_create(CLOCK_MONOTONIC)`
+ `SIGEV_PULSE_INIT` sur une période de 10 ms. Quelle est la **régularité
réelle** du tick, au repos et sous charge ?

**Méthode.** Le rm horodate **chaque tick** qu'il sert (`CLOCK_MONOTONIC`) et
tient : nombre de ticks, intervalle min/max/moyen, **écart maximal à la
période**, écart en ppm, nombre de ticks regroupés (intervalle > 2 périodes),
et latence de chaîne tick→verdict. Contrôle indépendant : la **sonde**
`tick_probe` arme le **même timer** (10 ms) sur **son propre canal** (aucun rm
impliqué) et compte les pulses reçus — elle sert à distinguer « le timer
n'est pas régulier » de « le rm perd des pulses ».

**Résultats bruts.**

| mesure | ticks | durée | taux | intervalle min | intervalle max | moyenne | **écart max** | **en ppm** | ticks regroupés | latence tick→verdict (max) |
|---|---|---|---|---|---|---|---|---|---|---|
| au repos | 2 219 | 22,7 s | **97,9 Hz** | 22 µs | 79 027 µs | 10 223 µs | **69 027 µs** | **6 902 700 ppm** | 22 | 2 µs |
| sous charge | 4 123 | 44,6 s | **92,4 Hz** | 3 µs | 103 085 µs | 10 826 µs | **93 085 µs** | **9 308 500 ppm** | 199 | 27 µs |
| sonde indépendante (sans rm) | 1 634 | 20,0 s | **81,7 Hz** | 5 µs | 548 873 µs | 12 241 µs | 538 873 µs | 53 887 300 ppm | 37 | — |

**Conclusions.**

1. **Le tick n'est pas régulier à 10 ms sur cette cible.** L'écart maximal à
   la période atteint **69 ms au repos** et **93 ms sous charge** (soit
   6,9 % et 9,3 % de la période), et le taux mesuré est **92 à 98 Hz** au
   lieu de 100 Hz.
2. **Ce n'est pas le rm qui perd les pulses.** La sonde indépendante, sur son
   propre canal et sans aucun rm, présente le même ordre de grandeur
   (81,7 Hz, écart max 549 ms). Le deficit vient donc de la cible
   virtualisée (contention de l'hôte : plusieurs autres machines QEMU
   tournaient en parallèle sur ce poste pendant la campagne), pas du code du
   rm.
3. **La chaîne elle-même est saine** : la latence tick→verdict côté serveur
   est de **2 µs au repos** et **27 µs sous charge**. Ce qui dérive, c'est
   l'**arrivée** du tick, pas son traitement.
4. **Conséquence médicale à retenir.** La borne « alarme haute en 200 ms »
   porte sur la **chaîne** (acquisition→verdict), et la chaîne respecte cette
   borne de très loin. Mais si l'**horloge d'acquisition** (le tick) peut
   être retardée de plus de 200 ms — ce qui a été observé, jusqu'à 549 ms sur
   la sonde indépendante — alors le **délai end-to-end** entre le
   phénomène physique et l'alarme peut dépasser 200 ms sur cette cible. La
   borne prouvée ne couvre donc **pas** le délai d'acquisition.

### 5.3 E4 — silence du capteur : **démontré** (watchdog « capteur muet »)

**Mécanisme.** Le rm arme un **deuxième timer noyau** (100 ms, indépendant
du tick d'acquisition) qui surveille le dernier échantillon reçu. Si aucun
échantillon n'arrive depuis plus de `X` ms (`--watchdog-ms X`, défaut
**1 000 ms**, `0` désactive), le rm émet une **alarme technique « capteur
muet »** dans sa borne `B_tech` (`bound=50 ms`). C'est le mécanisme
médicalement juste : **perte de signal** — et non « déconnexion », qui ne dit
rien de l'état du patient.

**Résultat sur cible** (rm lancé en `--no-tick`, donc la chaîne n'est
alimentée que par les clients) :

```
VERDICT_SILENCE:
WARN   VEILLE_TECHNICAL_ALARM  chain=/dev/veille  stage=acquire
       state=sensor_dead|bus_ok|prio_normal|alarm_none  bound=50  latency=15

VERDICT_SIGNAL:            (après retour d'un client qui écrit des échantillons)
INFO   VEILLE_OK  chain=/dev/veille  stage=alarm
       state=sensor_ok|bus_ok|prio_normal|alarm_none  bound=200
```

* l'alarme est **émise** après le seuil (silence mesuré 1 008–1 182 ms pour
  un seuil de 1 000 ms), avec `latency=15 ms` (≤ `B_tech` = 50 ms) ;
* elle **se lève** dès qu'un échantillon arrive (`sensor_ok`, verdict `OK`) ;
* compteur du rm : `wd_ms=1000`, `wd_count=2` (un épisode de silence avant
  le client, un après), `wd_fired=1`.

**Notification de disconnect par canal client — elle fonctionne, avec une
réserve.** Le noyau livre bien `_PULSE_CODE_DISCONNECT` au dispatch : le rm
l'intercepte dans sa boucle (le code −33 est hors de `[0,127]`, donc
`pulse_attach` ne peut pas l'attacher) et le compteur `n_disconnects` progresse
(2 notifications pour 3 ouvertures dans le journal E4). **Réserve honnête** :
cette notification ne distingue pas une **fermeture normale** d'une **mort
anormale** du client — chaque sortie de client la déclenche. Elle est donc
signalée comme « mort d'un pair » alors que le client a simplement fini son
travail ; dans un produit, il faut la corréler à l'état de la connexion
(`iofunc` ne fournit pas de callback de fermeture au rm) ou l'accepter comme
un simple « un client s'est déconnecté ».

### 5.4 E1 (rappel, non démontré)

Bornes et priorités IEC 60601-1-8 : **partiel**. Les ordres de grandeur
publics sont documentés dans `CONTRACT.md` ; la norme payante n'a pas été lue.
Aucune mesure nouvelle sur ce point.

## 6. Latences réelles sous charge (H2)

**Ce qui est mesuré.** La latence « échantillon → verdict » est mesurée
**deux fois**, par deux chemins indépendants :

1. **côté client** (méthode retenue pour les chiffres) : horodatage
   `CLOCK_MONOTONIC` avant et après l'écriture dans `/dev/veille`. Comme
   l'écriture est un `MsgSend`, elle ne rend la main qu'**après la réponse du
   rm** : le temps mesuré est l'**aller-retour réel**, qui inclut la file
   d'attente du dispatch, le traitement de la chaîne et l'aller-retour noyau.
   C'est la définition la plus honnête de « ce que vit le client ».
2. **côté serveur** (contrôle) : le rm horodate l'entrée de l'échantillon et
   la sortie du verdict (`target/port/qnx_time.c`), ce qui isole le temps de
   **chaîne** proprement dit.

Les deux sont rapportées : si elles divergent, l'écart est l'attente
(dispatch + ordonnancement), pas le traitement.

**Résultats bruts** (1000 échantillons par régime, µs).

| régime | n | p50 | p95 | p99 | **max** | min | moyenne | latence de chaîne côté serveur (max) |
|---|---|---|---|---|---|---|---|---|
| **au repos** | 1 000 | 35 | 67 | 200 | **5 250** | 14 | 49 | 3 µs (écritures) · 1 µs (ticks) |
| **sous charge** (client inondeur à 1 message en boucle) | 1 000 | 34 | 3 832 | 11 805 | **33 249** | 6 | 626 | 5 229 µs (151 246 écritures) |

**Lecture.**

* Au repos, la latence est de **35 µs au p50** et **200 µs au p99** : la borne
  prouvée de 200 ms pour l'alarme haute est tenue avec une marge de **1000×**
  au p99, et de **38×** au maximum observé (5,25 ms).
* Sous charge (un client écrit sans arrêt pendant la mesure), le p50 ne
  bouge pas (34 µs) mais la **queue** se forme : p95 = 3,8 ms, p99 = 11,8 ms,
  **max = 33,2 ms**. La **borne de 200 ms reste tenue** (max = 1/6 de la
  borne), mais elle n'est plus tenue avec une marge confortable.
* Le **traitement** de la chaîne, lui, reste marginal : 5,2 ms au maximum sur
  151 246 écritures sous charge, et 27 µs pour les ticks. Ce qui coûte, c'est
  l'ordonnancement et la file, pas la logique de décision.
* L'écart entre la latence client (p99 11,8 ms) et la latence serveur
  (max 5,2 ms) est l'attente du message dans le dispatch : le client attend
  que le rm ait fini l'échantillon qu'il traitait.

**Ce que ces chiffres ne disent pas.** La charge mesurée est **un seul client
logiciel** qui inonde le nœud. Elle ne couvre pas la charge d'un vrai moniteur
patient (capteur, ECG, réseau, stockage, interface). La latence **acquisition**
(le tick) n'est pas incluse dans ces chiffres : c'est l'objet du §5.2, et elle
n'est pas bornée à 200 ms sur cette cible.

## 7. Adaptive partitioning (C5) — **non réalisé, et pourquoi**

L'idée « isolation de la voie critique par partition adaptative » **n'est pas
mise en œuvre**, pour une raison vérifiable et non contournable :

- L'image **Quick Start Target Image** n'embarque **aucun** support du
  partitionneur : ni `aps`, ni `aps_client`, et **aucune** entrée de
  partitionnement dans son buildfile (`grep -i partition /proc/boot/build` ne
  renvoie rien). Le rm tourne donc dans une partition unique.
- L'activation exigerait de **reconstruire l'image** avec le partitionneur, ce
  qui échoue ici : la régénération de l'IFS par `mkqnximage` s'arrête sur les
  snippets `apk_root` absents de l'archive quickstart (« Non-directory 'bin' has
  child nodes » puis « Failed to create ifs boot image »), et le SDP du poste
  ne contient pas les paquets QNX Developer Desktop correspondants. Le serveur
  R630, où le SDP est complet, serait l'endroit idoine — mais la reconstruction
  de l'image n'y a pas été tentée dans le temps imparti.

**Ce qui tient lieu d'isolation, et ce qui n'existe pas** : la voie critique
est isolée par la **priorité** (SCHED_FIFO 62, voir `target/rm/resmgr_veille.c`)
et l'effet de l'héritage de priorité est mesuré (§5.1) ; l'isolation
**mémoire** par `secpol`/`abilities` n'est pas non plus en place. C'est un
manque assumé, pas une preuve.

## 8. Limites de cette preuve

- **Émulateur, pas du matériel** : la cible est un x86_64 virtualisé (KVM). Aucune
  mesure ne vaut pour un vrai moniteur patient ni pour une cible QNX embarquée.
- **Contention de l'hôte** : pendant la campagne, plusieurs autres machines
  virtuelles QEMU tournaient sur le même poste. Cela dégrade la cadence du
  timer (§5.2) et et probablement les queues de latence (§6). Les chiffres sont donc
  **pessimistes** par rapport à une machine dédiée — et **non reproductibles à
  l'identique** d'une exécution à l'autre (dérive de 82 à 98 Hz observée sur
  la sonde).
- **Signaux cliniques simulés à l'entrée du resource manager** : `/dev/veille`
  reçoit du bpm (déduit de l'ECG réel par le client). Le rejeu du signal brut
  (acquire → filter) n'est fait que par le jumeau Python.
- **Détection de pics R heuristique** (seuil adaptatif, non clinique) : les bpm
  extraits d'un ECG réel en fibrillation atriale oscillent fortement, et le
  « capteur figé » de la chaîne se déclenche dès que deux bpm consécutifs
  arrondis sont égaux — c'est un vrai enseignement des données réelles, à traiter
  au niveau du signal brut plutôt que du bpm.
- **Pas de trace noyau** : l'outil `traceprinter` du SDP installé refuse la
  trace capturée sur cible (*internal error code(12)*, format de trace plus
  récent que le SDP). E2 repose donc sur l'observation comportementale de la
  priorité, pas sur une trace.

## 9. Ce qui reste non démontré (à l'heure de cette rédaction)

| Point | État | Pourquoi |
|---|---|---|
| **E2 — garantie « le client prioritaire n'attend pas plus de X »** | **non démontrée** | L'héritage est observé (§5.1) mais l'attente maximale mesurée atteint 90 ms et aucune borne n'est établie. Le rm n'a pas de fil de service à priorité fixe. |
| **E3 — cadence 10 ms tenue** | **non démontrée (mesurée et défavorable)** | 92–98 Hz, écart max 69–103 ms sur cette cible virtualisée ; la sonde indépendante montre le même ordre de grandeur. |
| **E3 — délai end-to-end ≤ 200 ms** | **non démontré** | La borne prouvée ne couvre que la chaîne, pas l'attente du tick (jusqu'à 549 ms observés). |
| **E4 — silence du capteur** | **démontré** | Alarme technique « capteur muet » émise et levée (§5.3). |
| **E4 — notification de disconnect** | **démontrée mais grossière** | Elle arrive, mais ne distingue pas fermeture normale et mort du client. |
| **E1 — bornes IEC 60601-1-8** | **partiel** | Ordres de grandeur publics seulement ; la norme payante n'a pas été lue. |
| **Charge réaliste (capteur + ECG + réseau + stockage)** | **non mesurée** | La charge de preuve est logicielle (un client qui inonde le nœud). |
| **Trace noyau** | **capturée et décodée** | `tracelogger` (10 s, client SCHED_FIFO 63) puis `traceprinter -f` : 1 588 768 lignes décodées, 13 865 événements COMM attachés au rm (§5.1 bis). **Mais** cette image n'expose aucun événement de changement de priorité : la trace ne prouve pas l'héritage (la commande à retenir est `traceprinter -f fichier.kev`, l'argument positionnel est ignoré). |
| **Adaptive partitioning (C5)** | **non réalisé** | L'image quickstart n'embarque pas le partitionneur ; il faudrait reconstruire l'image avec `mkqnximage` (§7). |
| **Matériel réel (QNX sur RPi5 / aarch64)** | **non mesuré** | La compilation `gcc_ntoaarch64le` est prévue (`make qnx QCC_V=…`) mais non exécutée sur cible. |
