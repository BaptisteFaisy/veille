# Chapitre 6 — Protéger sa chaîne sur QNX 8.0

Objectif : séparer ce que le noyau QNX **garantit** de ce qu'il ne garantit **pas**, et apprendre à **mesurer** la différence sans kernel trace. Tout ce chapitre s'appuie sur les mesures réelles du projet Veille sur cible — les journaux sont dans [`preuve/qnx80/`](../preuve/qnx80/), le compte rendu dans [`docs/QNX-EVIDENCE.md`](../docs/QNX-EVIDENCE.md).

> ⚠️ Honnêteté, d'emblée. `docs/QNX-EVIDENCE.md` conclut sans détour : E2 est **observé mais partiellement quantifié**, E3 est **mesuré et défavorable** sur cette cible virtualisée, E4 est **démontré**. Ce chapitre ne fait que lire ces chiffres — il ne les embellit pas.

---

## 6.1 Ce que le noyau garantit, et ce qu'il ne garantit pas

Avant de coder, on fixe le partage des responsabilités. C'est le tableau qui a servi de boussole pour toute la campagne :

| Le noyau QNX **garantit** | Preuve (mesure sur cible) | Le noyau **ne garantit pas** |
|---|---|---|
| **Priority inheritance** pendant un `MsgSend` : le serveur tourne à la priorité de l'appelant | observé, 300/300 messages (§6.3) | la priorité **de base** du serveur ne le protège pas (§6.3, essais D/G) |
| **Timer noyau** (`timer_create` + `SIGEV_PULSE_INIT`) qui cadence l'acquisition | les pulses arrivent (§6.4) | la **régularité** de la cadence : 92–98 Hz au lieu de 100 Hz sur cette cible (§6.4) |
| **Notification de mort d'un pair** (`_PULSE_CODE_DISCONNECT`) | `n_disconnects` progresse (§6.5) | la **distinction** fermeture normale / mort anormale (§6.5) |
| **`CHANNEL` / `dispatch`** : messages et pulses servis dans une même boucle | chapitre 5, `dispatch_block` | — |

La règle de lecture : quand la première colonne est **vraie mais insuffisante**, c'est à nous d'ajouter la défense (watchdog, fil de service dédié) — ce chapitre montre comment.

## 6.2 La voie critique : `SCHED_FIFO`, priorité 62

Le resource manager se hisse en temps réel dès le démarrage :

```c
/* target/rm/resmgr_veille.c */
static void setup_priority(int prio) {
    struct sched_param sp;
    memset(&sp, 0, sizeof(sp));
    sp.sched_priority = prio;
    if (pthread_setschedparam(pthread_self(), SCHED_FIFO, &sp) != 0)
        fprintf(stderr, "[veille-rm] WARNING: priorité %d non appliquée\n", prio);
}
```

La priorité de base est une **constante nommée**, pas un chiffre en dur :

```c
/* target/rm/veille_rm.h */
#define VEILLE_PRIO_CRITICAL   62       /* priorité voie critique (SCHED_FIFO) */
```

`62` : c'est la valeur choisie pour que la voie critique capteur→alarme ne soit jamais préemptée par du travail best-effort (UI, journal, réseau). Mais — et c'est le point le plus contre-intuitif du projet — **cette priorité de base ne suffit pas à elle seule**.

La preuve tient en une ligne des journaux. Essai D (production, rm à 62, client prioritaire 40) :

```
prio_hist=0,0,0,0,0,134502,0,...,0,300,...
```

Lu de gauche à droite : le rm a reçu **134 502 messages à la priorité 5**, et **300 messages à la priorité 40**. C'est-à-dire que pendant tout le service d'un client inondeur à priorité 5, le noyau a fait tourner le rm **à la priorité 5**, pas à 62. La leçon est consignée dans `docs/QNX-EVIDENCE.md` §5.1.4 :

> « QNX 8.0 aligne la priorité du **receveur** sur celle de l'**émetteur** pendant le `MsgSend` : un client de faible priorité peut donc **déprioriser** le rm. Pour une voie critique réelle, il faut un fil de service dédié (priorité fixe) et non un dispatch monolithique. »

Autrement dit : `pthread_setschedparam(..., SCHED_FIFO, 62)` protège contre la **préemption par du travail moins prioritaire**, mais pas contre un **client moins prioritaire qui vous appelle** — car l'héritage est bidirectionnel. C'est l'objet de la section suivante.

## 6.3 L'héritage de priorité : ce que c'est, ce que ça change, comment on le mesure

### Ce que c'est

Quand un processus envoie un `MsgSend`, le noyau QNX élève **temporairement** le receveur à la priorité de l'émetteur, le temps de traiter le message. C'est le mécanisme anti-**inversion de priorité** : sans lui, un client prioritaire (40) pourrait rester bloqué derrière un serveur qui exécute du travail de priorité 5.

### Ce que ça change (mesuré, sans kernel trace)

Le kernel trace (`tracelogger`) s'est avéré **inexploitable** sur cette cible — `traceprinter` refuse le format de trace de l'image (`docs/QNX-EVIDENCE.md` §7 : *internal error code (12)*). Veille a donc choisi une preuve **comportementale** : le rm lit sa **propre priorité effective** au moment où il reçoit chaque message, et la range dans un histogramme.

```c
/* target/rm/rm_chain.c */
int veille_rm_prio_effective(veille_dev_t *dev) {
    int policy = 0;
    struct sched_param sp;
    memset(&sp, 0, sizeof(sp));
    if (pthread_getschedparam(pthread_self(), &policy, &sp) != 0) return -1;
    (void)dev;
    return sp.sched_priority;
}

void veille_rm_prio_observed(veille_dev_t *dev) {
    int p = veille_rm_prio_effective(dev);
    if (p < 0) return;
    dev->prio_effective = p;
    if (p >= 0 && p < VEILLE_PRIO_HIST_MAX) dev->prio_hist[p]++;
}
```

Et, pour le **contrôle négatif**, on annule explicitement le boost reçu :

```c
/* target/rm/rm_chain.c */
void veille_rm_prio_drop(veille_dev_t *dev) {
    struct sched_param sp;
    memset(&sp, 0, sizeof(sp));
    sp.sched_priority = dev->prio_base;
    if (pthread_setschedparam(pthread_self(), SCHED_FIFO, &sp) == 0) {
        dev->prio_dropped = 1;
        dev->prio_after_drop = veille_rm_prio_effective(dev);
    }
}
```

C'est l'option `--no-inherit` : "même noyau, même charge, même sonde — seul le boost diffère" (`docs/QNX-EVIDENCE.md` §5.1). Le `prio_after_drop` confirme que l'annulation a bien pris : **10** après drop, alors que la sonde tourne à 40.

### Les chiffres réels : A (héritage actif) contre B (héritage annulé)

Régime **saturé** (rm en file d'attente, hog SCHED_FIFO 30 + client inondeur), 300 échantillons par essai, aller-retour d'écriture en µs :

| Essai | Régime | p50 | p95 | p99 | max | Priorité vue par le rm (histogramme) |
|---|---|---|---|---|---|---|
| **A** `e2-a-sature-inherit` | saturé, héritage **actif** | 32 | **69** | **1 939** | 5 037 | 5 × 48 362 · 40 × 300 |
| **B** `e2-b-sature-noinherit` | saturé, héritage **annulé** | 34 | **5 634** | **12 879** | 29 885 | 5 × 123 699 · 40 × 300 (`prio_after_drop=10`) |

Ces chiffres sont lus tels quels depuis `preuve/qnx80/e2-a-sature-inherit-*.log` et `e2-b-sature-noinherit-*.log` (les percentiles `p50/p95/p99` sont ceux produits par `tools/qnx/analyse.py` sur ces journaux).

Ce qu'ils disent, sans enjoliver (`docs/QNX-EVIDENCE.md` §5.1) :

1. **Le mécanisme est observé.** À la réception des messages du client prioritaire, le rm s'exécute **à la priorité du client** (40, ou 20 dans l'essai C) — 300 messages par essai, **0 exception**.
2. **L'effet ne porte que sur la queue.** Le p50 est identique (32 vs 34 µs) : l'héritage ne rend pas le cas typique plus rapide. Mais le **p95 est 82× plus élevé sans héritage** (69 vs 5 634 µs) et le **p99 6,6× plus élevé** (1 939 vs 12 879 µs). Traduction : *l'héritage empêche le client prioritaire d'être affamé quand le rm est chargé*.
3. **Au repos, aucune différence mesurable** (essais E vs F : p95 5 100 vs 6 993 µs, p99 16 544 vs 13 547 µs — dans le bruit). Le boost ne gagne du temps que lorsque le rm a du travail en attente.

### Ce que ces chiffres ne disent pas

E2 n'est **pas** « vérifié » au sens fort : la garantie « le client prioritaire n'attend jamais plus de X » **n'est pas établie**. Au maximum observé, l'attente atteint **90 ms** (essai C, sonde priorité 20 **sous** le hog 30, `max = 90 086 µs`). C'est consigné ouvertement dans `docs/QNX-EVIDENCE.md` §8, et c'est la limite honnête de la méthode comportementale.

## 6.4 Pulses et timers : la cadence, et sa dérive mesurée

### Le mécanisme

L'acquisition est cadencée par un **timer noyau** qui envoie un **pulse** au dispatch. Un seul constructeur sert au tick d'acquisition et au timer de surveillance (zéro duplication) :

```c
/* target/rm/resmgr_veille.c */
static int setup_timer(int coid, int period_ms, int pulse_code, int prio) {
    struct sigevent ev;
    SIGEV_PULSE_INIT(&ev, coid, prio, pulse_code, 0);
    timer_t tid;
    if (timer_create(CLOCK_MONOTONIC, &ev, &tid) != 0) return -1;
    struct itimerspec it;
    memset(&it, 0, sizeof(it));
    it.it_value.tv_nsec = (long)period_ms * 1000000L;
    it.it_interval.tv_nsec = (long)period_ms * 1000000L;
    return timer_settime(tid, 0, &it, NULL);
}
```

Trois pièges d'API, tous appris **sur cible** et documentés dans `tools/qnx/README.md` §6 :

1. **`pulse_attach` SANS `MSG_FLAG_ALLOC_PULSE`**, avec un code **fixe** dans `[0,127]`. Avec le drapeau `ALLOC`, le dispatch alloue un code arbitraire et **ignore** celui demandé — alors que le timer envoie toujours vers celui écrit dans `SIGEV_PULSE_INIT`. Résultat : **le tick n'est jamais servi**, silencieusement. Le rm « vivait », le tick ne partait pas, et rien ne le signalait (`docs/QNX-EVIDENCE.md` §4.6).
2. **Le coid du timer vient du canal principal** (`message_connect(dpp, 0)`), pas d'un canal latéral : `dispatch_block()` ne sert pas le canal latéral (`docs/QNX-EVIDENCE.md` §4.7).
3. **`struct itimerspec` est en nanosecondes** : `it_value.tv_nsec = 10 ms` s'écrit `10000000`, pas `10000` (sinon le timer tourne 1000× trop vite).

Le code réel :

```c
/* target/rm/resmgr_veille.c */
    if (pulse_attach(dpp, 0, VEILLE_PULSE_TICK, pulse_tick, &veille_dev) < 0)
        return EXIT_FAILURE;
    ...
    int coid = message_connect(dpp, 0);   /* canal principal : dispatch_block le sert */
    if (coid < 0) return EXIT_FAILURE;
    /* Les pulses sont livrés à la priorité de base du rm : le boost de
     * priorité ne doit venir QUE du client (sinon la mesure E2 est faussée). */
    if (opts.tick && setup_timer(coid, VEILLE_PERIOD_MS, VEILLE_PULSE_TICK,
                                 opts.prio) != 0) return EXIT_FAILURE;
```

### La dérive mesurée (E3)

Le rm horodate **chaque tick** qu'il sert et tient ses statistiques (`target/rm/rm_chain.c`, `tick_stats_update`) : nombre de ticks, intervalle min/max/moyen, écart maximal à la période, écart en ppm, ticks regroupés.

Résultats bruts (`preuve/qnx80/e3-tick-repos-*.log` et `e3-tick-charge-*.log`) :

| Mesure | ticks | durée | taux | intervalle min | intervalle max | moyenne | **écart max** | **en ppm** | ticks regroupés | latence tick→verdict (max) |
|---|---|---|---|---|---|---|---|---|---|---|
| au repos | 2 219 | 22,7 s | **97,9 Hz** | 22 µs | 79 027 µs | 10 223 µs | **69 027 µs** | **6 902 700 ppm** | 22 | 2 µs |
| sous charge | 4 123 | 44,6 s | **92,4 Hz** | 3 µs | 103 085 µs | 10 826 µs | **93 085 µs** | **9 308 500 ppm** | 199 | 27 µs |
| sonde indépendante (sans rm) | 1 634 | 20,0 s | **81,7 Hz** | 5 µs | 548 873 µs | 12 241 µs | 538 873 µs | 53 887 300 ppm | 37 | — |

Le contrôle indépendant est la ligne du bas : la **sonde** `tick_probe` arme **le même timer** (10 ms) sur **son propre canal**, sans aucun rm impliqué :

```
tick_probe pulses=1634 duree_us=20000441 taux_hz=81.70 min_us=5 max_us=548873 moyenne_us=12241 maxdev_us=538873 coalesced=37
```

**Conclusion, sans enjoliver** (`docs/QNX-EVIDENCE.md` §5.2) :

1. **Le tick n'est pas régulier à 10 ms sur cette cible.** L'écart maximal atteint **69 ms au repos** et **93 ms sous charge**, et le taux mesuré est **92 à 98 Hz** au lieu de 100 Hz.
2. **Ce n'est pas le rm qui perd les pulses.** La sonde indépendante, sur son propre canal et sans rm, présente le même ordre de grandeur (81,7 Hz, écart max 549 ms). Le déficit vient de la cible virtualisée (contention de l'hôte), pas du code.
3. **La chaîne elle-même est saine** : la latence tick→verdict côté serveur est de **2 µs au repos** et **27 µs sous charge**. Ce qui dérive, c'est l'**arrivée** du tick, pas son traitement.
4. **Conséquence médicale à retenir.** La borne « alarme haute en 200 ms » porte sur la **chaîne** (acquisition→verdict), et la chaîne respecte cette borne de très loin. Mais si l'**horloge d'acquisition** peut être retardée de plus de 200 ms — ce qui a été observé, jusqu'à 549 ms sur la sonde indépendante — alors le **délai end-to-end** entre le phénomène physique et l'alarme peut dépasser 200 ms sur cette cible. **La borne prouvée ne couvre donc pas le délai d'acquisition** (`docs/QNX-EVIDENCE.md` §8 : « E3 — délai end-to-end ≤ 200 ms : non démontré »).

> 💡 C'est exactement le genre d'écart que le chapitre 1 dénonçait : une mesure ponctuelle (« le tick est à 10 ms ») ne dit rien du pire cas. Ici, c'est l'inverse qui est démontré : la **chaîne** est saine, mais l'**horloge** ne l'est pas.

## 6.5 Le watchdog « capteur muet » : la défense qui ne dépend pas du tick

Face à une horloge d'acquisition **qui peut dériver**, et à un capteur qui peut **mourir en silence**, la chaîne a besoin d'une défense qui n'emprunte **pas** le chemin défaillant. C'est le watchdog « capteur muet » : un **deuxième timer noyau** (100 ms), indépendant du tick d'acquisition, qui surveille le dernier échantillon reçu.

```c
/* target/rm/rm_chain.c */
void veille_rm_watchdog(veille_dev_t *dev) {
    long now = veille_now_us();
    if (dev->wd_ms <= 0) return;                 /* surveillance désactivée */
    if (dev->wd_last_us <= 0) { dev->wd_last_us = now; return; }
    long silence_ms = (now - dev->wd_last_us) / 1000L;
    dev->wd_silence_ms = silence_ms;
    if (silence_ms < dev->wd_ms || dev->wd_fired) return;
    dev->wd_fired = 1;
    dev->wd_count++;
    char msg[96];
    snprintf(msg, sizeof(msg),
             "capteur muet — aucun échantillon depuis %ld ms (seuil %d ms)",
             silence_ms, dev->wd_ms);
    veille_rm_set_tech(dev, VEILLE_TECH_SILENCE, msg, VEILLE_SENSOR_DEAD,
                       dev->cfg.bound_tech_ms, (long)dev->cfg.tech_detect_ms);
    format_verdicts(dev, NULL, 0);   /* réaffiche le rapport avec l'alarme */
    fprintf(stderr, "[veille-rm] ALARME TECHNIQUE : %s\n", msg);
}
```

La clé est dans le **déclenchement** : le timer de surveillance est armé séparément du tick, avec une période **plus grande** (100 ms) mais un seuil **encore plus grand** (`--watchdog-ms`, défaut 1 000 ms) :

```c
/* target/rm/veille_rm.h */
#define VEILLE_WD_MS_DEFAULT   1000     /* silence capteur : seuil par défaut */
#define VEILLE_WD_PERIOD_MS    100      /* période du timer de surveillance */
```

Le résultat mesuré sur cible (E4, rm en `--no-tick`, donc la chaîne n'est alimentée **que** par les clients — `preuve/qnx80/e4-retour-signal-20261112T204646Z.log`) :

```
VERDICT_SILENCE:
WARN   VEILLE_TECHNICAL_ALARM  chain=/dev/veille  stage=acquire  state=sensor_dead|bus_ok|prio_normal|alarm_none  bound=50  latency=15
OK
VERDICT_SIGNAL:
INFO   VEILLE_OK  chain=/dev/veille  stage=alarm  state=sensor_ok|bus_ok|prio_normal|alarm_none  bound=200
OK
```

Et les compteurs du rm (`preuve/qnx80/e4-stats-20261112T204652Z.log`) :

```
wd_ms=1000
wd_count=2
wd_fired=1
wd_silence_ms=1182
```

Lecture :

- l'alarme est **émise** après le seuil (silence mesuré **1 008 à 1 182 ms** pour un seuil de 1 000 ms), avec `latency=15 ms` — c'est-à-dire **≤ `B_tech` = 50 ms** ;
- elle **se lève** dès qu'un échantillon arrive (`sensor_ok`, verdict `OK`) : le retour du signal réarme le watchdog ;
- `wd_count=2` = deux épisodes de silence (avant et après le client qui écrit).

C'est la réponse correcte, médicalement, à la **perte de signal** : IEC 60601-1-8 exige une alarme technique, pas un silence. Et comme ce watchdog est un timer noyau **indépendant**, il fonctionne même en mode `--no-tick` (chaîne pilotée par les seuls clients) — c'est-à-dire précisément dans le cas où l'horloge d'acquisition a disparu.

> ⚠️ **La notification de disconnect, elle, est démontrée mais grossière** (`docs/QNX-EVIDENCE.md` §5.3) : le noyau livre bien `_PULSE_CODE_DISCONNECT` (le rm l'intercepte dans sa boucle, `n_disconnects=2` pour 3 ouvertures), mais elle ne distingue pas une **fermeture normale** d'une **mort anormale** du client. Chaque sortie de client la déclenche. Dans un produit, il faut soit la corréler à l'état de la connexion, soit l'accepter comme un simple « un client s'est déconnecté ». Le watchdog « capteur muet » reste la défense primaire ; le disconnect est un signal secondaire.

## 6.6 Ce que tient la chaîne sous charge (H2, pour mémoire)

Complément utile : la latence **échantillon → verdict** mesurée par deux chemins indépendants (`docs/QNX-EVIDENCE.md` §6). Résultats réels (1 000 échantillons par régime, µs) :

| Régime | p50 | p95 | p99 | max | latence de chaîne côté serveur (max) |
|---|---|---|---|---|---|
| au repos | 35 | 67 | 200 | 5 250 | 3 µs (écritures) · 1 µs (ticks) |
| sous charge (client inondeur) | 34 | 3 832 | 11 805 | 33 249 | 5 229 µs (151 246 écritures) |

Points clés :

- Au repos, la borne prouvée de 200 ms est tenue avec une marge de **1000× au p99** et **38× au maximum observé**.
- Sous charge, la **borne de 200 ms reste tenue** (max = 1/6 de la borne), mais la marge rétrécit : le coût vient de l'ordonnancement et de la file, pas du traitement (5,2 ms max côté serveur).
- L'écart p99 client (11,8 ms) vs serveur (5,2 ms) est l'**attente du message dans le dispatch**.

Ces chiffres ne couvrent qu'**un seul client logiciel** qui inonde le nœud — pas la charge d'un vrai moniteur (capteur, ECG, réseau, stockage). Et ils n'incluent **pas** le délai d'acquisition du tick (§6.4) : `docs/QNX-EVIDENCE.md` §6 le dit noir sur blanc.

## 6.7 Exercice « à toi » : mesurer la dérive de TON timer

**Énoncé.** La sonde `tick_probe` (`tools/qnx/tick_probe.c`) arme un timer 10 ms sur son propre canal et compte les pulses reçus, sans aucun rm. Démontre, **par la mesure**, la régularité réelle du timer sur **ta** cible (la tienne, pas celle de la campagne).

Compile d'abord l'outil (si ce n'est pas déjà fait) :

```
bash tools/qnx/build.sh            # → build/qnx/{veille-rm,bench_client,hog,tick_probe}
```

Puis lance la VM et la sonde :

```
bash tools/qnx/boot.sh --start     # VM QNX 8.0, attend le SSH
# …pousser build/qnx/tick_probe dans l'invité (voir tools/qnx/README.md §3)…
./tick_probe --period-ms 10 --duration-ms 20000
```

**Ce que tu dois lire** — la sortie attendue a **cette forme** (la valeur de référence de la campagne, `preuve/qnx80/e3-sonde-independante-20261112T204615Z.log`) :

```
tick_probe pulses=1634 duree_us=20000441 taux_hz=81.70 min_us=5 max_us=548873 moyenne_us=12241 maxdev_us=538873 coalesced=37
```

**Le critère de réussite** — les trois questions auxquelles tu dois répondre **avec tes chiffres** :

1. **Taux** : `taux_hz` est-il proche de 100 Hz ? (sur la cible émulée de la campagne : **81,7 Hz** — on attend donc un déficit visible.)
2. **Pire cas** : `max_us` / `maxdev_us` dépasse-t-il la période de 10 ms ? Si oui, de combien ? (référence : écart max **538 873 µs** ≈ 539 ms.)
3. **Coalescence** : `coalesced` (échantillons groupés, intervalle > 2 périodes) est-il non nul ? (référence : **37**.)

Ensuite, la vraie leçon : **fais tourner le rm lui-même** sous la même charge, et compare `tick_maxdev_us` dans son canal de mesures (`bench_client stats`) :

```
./bench_client stats
# → relève tick_maxdev_us=… tick_coalesced=… ticks=…
```

**Conclusion attendue.** Si ton `tick_probe` montre la même dérive que ton `veille-rm`, la cause est la **cible** (virtualisation, contention de l'hôte), pas ton code — c'est la conclusion exacte de `docs/QNX-EVIDENCE.md` §5.2. Si en revanche `tick_probe` est nickel et le rm dérive, c'est ton rm qui **perd des pulses** : cherche un `MSG_FLAG_ALLOC_PULSE` ou un canal latéral (§6.4), les deux causes déjà piégées dans ce projet.

> 💡 Pour être honnête et reproductible, le banc complet de la campagne se relance en une commande : `bash tools/qnx/run-bench.sh all` (E3, E4, H2, E2), puis `python3 tools/qnx/analyse.py preuve/qnx80`. Ta mesure devra **s'ajouter** aux journaux, pas les remplacer.

## 6.8 Ce que vous avez maintenant

- Un tableau de bord **garanti / non garanti** : priority inheritance (observée), timer noyau (irrégulier sur cible émulée), disconnect (grossier), `dispatch_block` (fiable).
- La preuve **comportementale** de l'héritage de priorité (histogramme de priorités effectives, contrôle négatif `--no-inherit`), avec les vrais chiffres : **p95 69 vs 5 634 µs (82×)**, p99 1 939 vs 12 879 µs (6,6×).
- La dérive du timer **mesurée** (97,9 Hz au repos, écart max 69 ms), et le réflexe du **contrôle indépendant** (`tick_probe` sur canal dédié) pour attribuer la cause.
- Le **watchdog « capteur muet »** démontré (alarme technique en `B_tech=50 ms` après ~1 s de silence, levée au retour du signal).

La morale du projet tient en une phrase : **le noyau fournit des mécanismes, pas des garanties de bout en bout — c'est à la chaîne d'ajouter les défenses (watchdog, fil de service dédié) et de les mesurer pour de vrai.**

← [Chapitre 5 : Écrire un resource manager QNX 8.0](05-ecrire-un-resource-manager-qnx.md) · [Sommaire](README.md)
