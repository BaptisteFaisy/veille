# Chapitre 5 — Écrire un resource manager QNX 8.0

Objectif : transformer le pipeline portable `target/pipe/` en un **vrai resource manager** QNX 8.0 qui publie `/dev/veille`, et survivre aux cinq pièges qui ont coûté une journée de mise au point sur la cible réelle.

> Ce chapitre est **autonome** : il part du code du dépôt (`target/rm/`) et montre les vraies corrections. Tous les extraits sont copiés depuis les fichiers du dépôt ; les chemins sont indiqués à chaque fois. Les chiffres viennent des journaux de [`preuve/qnx80/`](../preuve/qnx80/) et de [`docs/QNX-EVIDENCE.md`](../docs/QNX-EVIDENCE.md).

---

## 5.1 Ce que le pipeline portable vous a déjà fait gagner

Le cœur de Veille est portable par construction : `core/` ne lit ni horloge, ni fichier, ni socket ; la chaîne `acquire → filter → decide` vit dans un seul fichier partagé entre la simulation hôte et la cible QNX.

```c
/* target/pipe/veille_pipe.c */
void veille_pipe_default_config(veille_chain_config *cfg) {
    if (!cfg) return;
    memset(cfg, 0, sizeof(*cfg));
    cfg->priority = VEILLE_PRIO_HIGH;
    cfg->bound_alarm_ms = 200;      /* >= pire cas absolu 165 ms → preuve complète */
    cfg->bound_ack_ms = 60000;
    cfg->bound_tech_ms = 50;
    cfg->tech_detect_ms = 15;
    cfg->stage_latency_ms[VEILLE_STAGE_ACQUIRE] = 5;
    cfg->stage_latency_ms[VEILLE_STAGE_FILTER] = 10;
    cfg->stage_latency_ms[VEILLE_STAGE_DECIDE] = 10;
    cfg->stage_latency_ms[VEILLE_STAGE_ALARM] = 20;
    cfg->stage_latency_ms[VEILLE_STAGE_ACK] = 5;
}
```

C'est ici qu'est gelée la **borne de 200 ms** que le chapitre 3 a prouvée : le resource manager ne l'invente pas, il la reçoit du cœur portable.

Le resource manager n'a donc **rien** à réinventer : il doit seulement (1) recevoir des échantillons, (2) les horodater, (3) appeler la chaîne, (4) rendre le verdict. La colle QNX tient dans cinq fichiers : `target/rm/resmgr_veille.c` (main, dispatch, timers, options), `target/rm/rm_io.c` (handlers `io_read` / `io_write` / `open` + canal de mesures), `target/rm/rm_chain.c` (enchaînement, verdicts, watchdog, mesures), `target/rm/veille_rm.h` (état partagé) et `target/rm/veille_rm_protocol.h` (constantes partagées avec les clients).

Et l'horloge est la seule divergence hôte/cible :

```c
/* target/port/qnx_time.c */
#define _POSIX_C_SOURCE 200112L
#include "port_time.h"
#include <time.h>

long veille_now_us(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return ts.tv_sec * 1000000L + ts.tv_nsec / 1000;
}
```

> ⚠️ `200112L` et non `199309L` : sur QNX 8.0, `CLOCK_MONOTONIC` est POSIX-2001. Avec `-std=c11` strict, `199309L` ne suffit pas (contrairement à glibc). C'est documenté dans `docs/QNX-BUILD.md` §3.

## 5.2 Le squelette minimal : `dispatch`, `resmgr_attach`, `iofunc_open_default`

Le point de départ réel du dépôt — `target/rm/resmgr_veille.c`, fonction `main` :

```c
/* target/rm/resmgr_veille.c */
int main(int argc, char **argv) {
    veille_rm_opts opts;
    parse_options(argc, argv, &opts);

    veille_rm_init(&veille_dev);
    veille_dev.prio_base = opts.prio;
    veille_dev.prio_effective = opts.prio;
    veille_dev.wd_ms = opts.watchdog_ms;
    veille_dev.no_inherit = opts.no_inherit;
    setup_priority(opts.prio);

    dispatch_t *dpp = dispatch_create();
    if (!dpp) return EXIT_FAILURE;

    /* handlers iofunc : défauts + read/write de la chaîne (rm_io.c) */
    resmgr_connect_funcs_t connect_funcs;
    resmgr_io_funcs_t io_funcs;
    iofunc_func_init(_RESMGR_CONNECT_NFUNCS, &connect_funcs,
                     _RESMGR_IO_NFUNCS, &io_funcs);
    io_funcs.read = veille_io_read;
    io_funcs.write = veille_io_write;
    connect_funcs.open = veille_open;   /* comptage des clients connectés */

    resmgr_attr_t rattr;
    memset(&rattr, 0, sizeof(rattr));
    if (resmgr_attach(dpp, &rattr, VEILLE_MOUNT_POINT, _FTYPE_ANY, 0,
                      &connect_funcs, &io_funcs, &veille_dev.attr) < 0)
        return EXIT_FAILURE;
```

Deux choses à noter, toutes vérifiées dans les en-têtes du SDP 8.0 :

1. **`resmgr_attach` prend 8 arguments et renvoie un `int`** — pas un `resmgr_connection_t *`. L'échec est `< 0`. Le chapitre 4 (écrit avant la compilation croisée) supposait l'API 7.x ; le tableau de correspondance est dans `docs/QNX-BUILD.md` §6.
2. **L'`iofunc_attr_t` doit être le PREMIER membre** de la structure d'état, parce que `RESMGR_HANDLE_T` est casté en `iofunc_attr_t *`. D'où le commentaire `/* attr = premier membre */` qui revient dans tout le code du dépôt.

`iofunc_func_init` installe par ailleurs les handlers par défaut (`iofunc_open_default`, `iofunc_read_default`, `iofunc_write_default`…) : on ne remplace que ce qu'on sait faire — ici `read`, `write` et `open`.

Le handler `open` réel :

```c
/* target/rm/rm_io.c */
int veille_open(resmgr_context_t *ctp, io_open_t *msg, RESMGR_HANDLE_T *handle, void *extra) {
    veille_dev_t *dev = (veille_dev_t *)handle;   /* attr = premier membre */
    int status = iofunc_open_default(ctp, msg, handle, extra);
    if (status == EOK) veille_rm_note_client(dev, 1);
    return status;
}
```

`iofunc_open_default` doit **être appelé** : c'est lui qui alloue l'OCB, initialise les attributs et gère le mode d'ouverture. Ne le pas appeler = pas d'OCB = crash au premier `read`.

Enfin, la boucle de service, qui mélange messages clients et pulses noyau :

```c
/* target/rm/resmgr_veille.c */
    dispatch_context_t *ctp = dispatch_context_alloc(dpp);
    if (!ctp) return EXIT_FAILURE;
    for (;;) {
        ctp = dispatch_block(ctp);
        if (!ctp) break;
        if (is_disconnect(ctp)) { veille_rm_peer_lost(&veille_dev); continue; }
        dispatch_handler(ctp);
    }
    dispatch_context_free(ctp);
    return EXIT_SUCCESS;
}
```

`dispatch_block` / `dispatch_handler` (et non `resmgr_block` / `resmgr_handler`) : c'est la seule façon de **servir les pulses ET les messages clients** dans la même boucle.

## 5.3 Le piège n°1 : `io_write` ne retourne pas le nombre d'octets

C'est le défaut le plus coûteux du projet, et il est **invisible** : le serveur compile, démarre, répond — mais le client reçoit une erreur.

### La version fausse

Voici le handler **tel qu'il a été écrit la première fois** (git `55c3f97`, `target/rm/rm_io.c`) :

```c
/* version FAUSSE — target/rm/rm_io.c (git 55c3f97) */
int veille_io_write(resmgr_context_t *ctp, io_write_t *msg, RESMGR_OCB_T *ocb) {
    int status = iofunc_write_verify(ctp, msg, ocb, NULL);
    if (status != EOK) return status;
    if ((msg->i.xtype & _IO_XTYPE_MASK) != _IO_XTYPE_NONE) return ENOSYS;
    unsigned nb = msg->i.nbytes;
    if (nb == 0 || nb >= VEILLE_WRITE_CAP) return EINVAL;

    /* write-combining : les données suivent l'en-tête io_write_t. */
    char buf[VEILLE_WRITE_CAP];
    memcpy(buf, (const char *)(msg + 1), nb);
    buf[nb] = '\0';

    long bpm;
    if (!parse_sample(buf, &bpm)) return EINVAL;
    veille_rm_push((veille_dev_t *)ocb->attr, bpm);  /* horodaté côté serveur */
    return _IO_SET_WRITE_NBYTES(ctp, nb);            /* status = nb écrits */
}
```

Le problème est **le dernier `return`**. Regardons la macro du SDP 8.0 (`$QNX_SDP/target/qnx/usr/include/sys/iomsg.h` ligne 446) :

```c
#define _IO_SET_WRITE_NBYTES(_c, _s)	_RESMGR_STATUS(_c, _s)
```

et (`sys/resmgr.h` ligne 217) :

```c
#define _RESMGR_STATUS(_c,_s)	((_c)->status = (_s))
```

`_RESMGR_STATUS` est une **affectation**. En C, une affectation est une expression dont la valeur est celle affectée. Donc `_IO_SET_WRITE_NBYTES(ctp, nb)` :

1. **pose** `ctp->status = nb` (le bon effet), **et**
2. **retourne** `nb` — le nombre d'octets.

`return _IO_SET_WRITE_NBYTES(ctp, nb);` retourne donc **`nb`**, et un retour positif du handler `write` est interprété par le noyau comme un **errno à renvoyer au client**. Le client reçoit donc un errno **déduit de la taille de son écriture** :

| Écriture | `nb` | errno reçu par le client |
|---|---|---|
| `"bpm 72\n"` | 7 | `E2BIG` (7) — *Argument list too long* |
| `"bpm 132\n"` | 8 | `ENOEXEC` (8) — *Exec format error* |
| `"bpm 7\n"` | 6 | `ENXIO` (6) — *No such device or address* |

Ces trois valeurs sont bien les `errno` QNX 8.0 (`$QNX_SDP/target/qnx/usr/include/errno.h` lignes 57-59 : `ENXIO 6`, `E2BIG 7`, `ENOEXEC 8`). Le compte rendu `docs/QNX-EVIDENCE.md` §4.1 le formule ainsi : « *le client recevait donc `EINVAL`-like : `E2BIG` pour 7 octets, `ENOEXEC` pour 8, `ENXIO` pour 6 — c'est-à-dire un errno déduit de la taille de l'écriture* ».

La version corrigée pose le statut puis retourne `EOK`, en deux lignes — le pattern officiel du SDP (`s1_resmgr_write_simple`) :

```c
/* version CORRECTE — target/rm/rm_io.c (HEAD) */
    _IO_SET_WRITE_NBYTES(ctp, nb);   /* pose ctp->status ; ne PAS le retourner */
    return EOK;                      /* retour positif = errno côté client */
```

> 💡 Règle à retenir : **`return` d'un handler `write` = un errno, pas une taille.** Pour dire « j'ai écrit `nb` octets », on pose `ctp->status` via `_IO_SET_WRITE_NBYTES` et on retourne `EOK`. Même remarque pour `read` : le retour est `_RESMGR_NPARTS(1)` (un nombre de parties, négatif), pas le nombre d'octets — les octets passent par `_IO_SET_READ_NBYTES`.

## 5.4 Le piège n°2 : les données ne sont pas forcément collées à l'en-tête

La version fausse ci-dessus fait :

```c
memcpy(buf, (const char *)(msg + 1), nb);   /* FAUX */
```

Cela suppose que le noyau a collé les données **juste après** l'en-tête `io_write_t`. Ce n'est pas garanti : la mise en page du message peut être modifiée par le noyau (write-combining), et les données peuvent se trouver ailleurs dans le tampon.

Le SDP fournit la primitive qui gère ce cas :

```c
/* version CORRECTE — target/rm/rm_io.c (HEAD) */
    size_t nb = _IO_WRITE_GET_NBYTES(msg);
    if (nb == 0 || nb >= VEILLE_WRITE_CAP) return EINVAL;

    /* Les données ne sont PAS forcément contiguës à l'en-tête : on les lit par
     * resmgr_msgget (pattern officiel du SDP, s1_resmgr_write_simple). */
    char buf[VEILLE_WRITE_CAP];
    if (resmgr_msgget(ctp, buf, nb, sizeof(msg->i)) == -1) return errno;
    buf[nb] = '\0';
```

Trois détails :

- `sizeof(msg->i)` est la **taille de l'en-tête** : c'est l'offset où commencent les données dans le message. On le passe à `resmgr_msgget` pour qu'il recopie **depuis le bon endroit**, message par message.
- `resmgr_msgget` renvoie `-1` en cas d'échec : on relaie `errno` au client (`return errno;`), sinon on perdrait l'information.
- `_IO_WRITE_GET_NBYTES(msg)` (au lieu de `msg->i.nbytes`) gère proprement le cas 64 bits (`_IO_WRITE64`) sur les cibles 64 bits.

## 5.5 Le piège n°3 : une écriture peut contenir un lot d'échantillons

Un client qui écrit **en tampon** (le cas du client Python `host/veille/resmgr_client.py`) envoie plusieurs lignes dans un seul `write()`. La version fausse, qui n'acceptait qu'**une** valeur, répondait `EINVAL` et perdait des battements.

La version corrigée parse **tout** le lot, et **une ligne invalide rejette l'écriture entière** (aucune moitié n'est poussée) — au même esprit que la règle du `CONTRACT.md` §1 : « *Toute erreur arrête la chaîne et produit un verdict — jamais de reprise approximative sur un échantillon partiellement compris* ».

```c
/* target/rm/rm_io.c */
static int parse_lot(char *buf, long *valeurs, int cap) {
    int n = 0;
    for (char *ligne = strtok(buf, "\n"); ligne; ligne = strtok(NULL, "\n")) {
        if (n >= cap) return -EINVAL;
        long bpm;
        if (!parse_sample(ligne, &bpm)) return -EINVAL;
        valeurs[n++] = bpm;
    }
    return n;
}
```

Le plafond de lot est une constante du protocole, pas un magic number :

```c
/* target/rm/veille_rm.h */
#define VEILLE_WRITE_CAP       4096     /* taille max d'une écriture (octets) */
#define VEILLE_BATCH_MAX       256      /* échantillons max par écriture */
```

Et l'appel :

```c
/* target/rm/rm_io.c */
    long valeurs[VEILLE_BATCH_MAX];
    int n = parse_lot(buf, valeurs, VEILLE_BATCH_MAX);
    if (n < 0) return -n;                       /* -EINVAL → EINVAL */
    ...
    for (int i = 0; i < n; i++) veille_rm_push(dev, valeurs[i]);  /* horodaté serveur */
```

> 💡 `parse_lot` renvoie `-EINVAL` et l'appelant fait `return -n;` : la convention « retour négatif = code d'erreur à propager » évite de se tromper de signe. Un `return n;` aurait renvoyé `256` comme errno.

## 5.6 Le handler `io_read` : position, EOF, `_RESMGR_NPARTS(1)`

`read()` sur `/dev/veille` renvoie le **verdict courant au format texte du contrat**. Le handler réel :

```c
/* target/rm/rm_io.c */
int veille_io_read(resmgr_context_t *ctp, io_read_t *msg, RESMGR_OCB_T *ocb) {
    int status = iofunc_read_verify(ctp, msg, ocb, NULL);
    if (status != EOK) return status;
    if ((msg->i.xtype & _IO_XTYPE_MASK) != _IO_XTYPE_NONE) return ENOSYS;

    veille_dev_t *dev = (veille_dev_t *)ocb->attr;   /* attr = premier membre */
    long off = (long)ocb->offset;
    /* Canal de mesures (tools/qnx/) : offset réservé, ne touche pas au verdict. */
    if (off == VEILLE_STATS_OFFSET) {
        static char stats[VEILLE_STATS_CAP];   /* un seul serveur, un seul fil */
        veille_rm_stats_text(dev, stats, sizeof(stats));
        size_t len = strlen(stats);
        int nb = ((long)msg->i.nbytes < (long)len) ? (int)msg->i.nbytes : (int)len;
        SETIOV(ctp->iov + 0, stats, nb);
        ocb->offset += nb;
        _IO_SET_READ_NBYTES(ctp, nb);
        return _RESMGR_NPARTS(1);
    }

    int nb = 0;
    if (off < dev->report_len) {
        long avail = dev->report_len - off;
        nb = ((long)msg->i.nbytes < avail) ? (int)msg->i.nbytes : (int)avail;
    }
    SETIOV(ctp->iov + 0, dev->report + off, nb);     /* nb == 0 → EOF */
    ocb->offset += nb;
    _IO_SET_READ_NBYTES(ctp, nb);
    return _RESMGR_NPARTS(1);
}
```

Les cinq règles qu'il faut comprendre :

1. **`iofunc_read_verify` d'abord.** Il vérifie le type d'I/O, les droits, le mode non bloquant, et calcule `msg->i.nbytes`. On ne l'écourte pas.
2. **La position est dans `ocb->offset`, pas dans le message.** L'offset est **par client** (un OCB par ouverture) : c'est ce qui permet à deux clients de lire le verdict sans se marcher dessus. On rend le **minimum** de `nbytes` et de ce qui reste, et on avance `ocb->offset` de ce qu'on a rendu.
3. **`SETIOV(ctp->iov + 0, …)` décrit la partie de réponse.** On ne copie rien : on dit au noyau « le client doit lire `nb` octets à cette adresse ». C'est un **zéro-copy** : le noyau écrit directement dans le tampon du client.
4. **`_IO_SET_READ_NBYTES(ctp, nb)`** pose le nombre d'octets rendus, et **`return _RESMGR_NPARTS(1)`** dit « réponds avec **1** partie ». Le retour du handler `read` est donc un **nombre de parties**, pas un errno : d'où l'importance de ne pas confondre avec `write` (§5.3).
5. **`nb == 0` = fin de fichier.** Si l'offset est déjà à la fin du rapport, on rend 0 octet : le client voit `read()` retourner 0, sémantique POSIX de l'EOF. Sans ça, le client bouclerait à l'infini.

Le `lseek` est indispensable : après un `read()`, l'offset de l'OCB est en fin de rapport ; il faut revenir à 0 pour relire le verdict courant — c'est ce que fait le client de mesure (`tools/qnx/bench_client.c`, mode `verdict`), et c'est le piège listé en §6.5 de `tools/qnx/README.md`.

### Un offset réservé pour les mesures

Le chemin de lecture a **deux** branches, séparées par un offset réservé :

```c
/* target/rm/veille_rm_protocol.h */
#define VEILLE_MOUNT_POINT    "/dev/veille"
#define VEILLE_STATS_OFFSET   0x40000000L      /* offset read() réservé au canal de mesures */
```

Le verdict (offset 0) est le **format du CONTRAT** ; l'offset `0x40000000` rend un texte `cle=valeur` **hors contrat**, réservé à l'outillage de preuve. Cette séparation est volontaire : le format figé du `CONTRACT.md` §6.1 ne doit **jamais** être pollué par des compteurs de mesure. C'est ce qui permet de lire les compteurs du serveur sans toucher au format gelé :

```c
/* tools/qnx/bench_client.c */
static int print_stats(int fd) {
    static char buf[8192];
    memset(buf, 0, sizeof(buf));
    if (lseek(fd, VEILLE_STATS_OFFSET, SEEK_SET) < 0) { ... }
    int n = read(fd, buf, sizeof(buf) - 1);
    ...
```

## 5.7 L'horodatage côté serveur et la réponse au format du contrat

Deux décisions structurantes.

### (a) C'est le serveur qui horodate, pas le client

Le client écrit `bpm 132` : **rien** sur l'instant de la mesure. C'est le serveur qui horodate **à la réception**, avec son horloge monotone :

```c
/* target/rm/rm_chain.c */
static void push_sample(veille_dev_t *dev, long raw_bpm, int from_tick) {
    long t0 = veille_now_us();                       /* horodatage d'arrivée */
    veille_pipe_result r = veille_pipe_push(&dev->pipe, raw_bpm);
    long dt_ms = (veille_now_us() - t0) / 1000;      /* L_measured */
    dev->n_samples++;
    lat_note(dev, veille_now_us() - t0, from_tick);
    dev->wd_last_us = veille_now_us();               /* le capteur parle : on réarme */
    dev->wd_fired = 0;
    veille_rm_clear_tech(dev, VEILLE_TECH_SILENCE);   /* le signal est revenu */
```

Pourquoi côté serveur ? Parce que l'horloge du client n'est **pas** l'horloge de la chaîne : entre le `write()` du client et l'horodatage, il y a la file d'attente du dispatch et l'ordonnancement. Horodater à la réception, c'est mesurer **ce que vit la chaîne**, pas ce que vit le client. L'aller-retour complet (client → dispatch → chaîne → réponse) est mesuré **séparément**, côté client (§5.8).

> 💡 C'est la traduction directe de la règle « `core/` ne lit aucune horloge » : le cœur calcule des latences *fournies*, la couche cible *mesure*. `target/port/qnx_time.c` est la seule porte d'entrée de l'horloge sur la cible.

### (b) La réponse est au format texte du CONTRAT, rien d'autre

Le verdict est mis en forme par le code **pur et testé** du cœur, pas par une chaîne `sprintf` dans le resource manager :

```c
/* target/rm/rm_chain.c */
static void format_verdicts(veille_dev_t *dev, const veille_verdict *v, size_t n) {
    veille_verdict all[3];
    size_t k = 0;
    for (size_t i = 0; i < n && k < 2; i++) all[k++] = v[i];
    if (dev->tech_kind != VEILLE_TECH_NONE && k < 3) all[k++] = dev->tech_v;
    long len = veille_report_text(all, k, dev->report, sizeof(dev->report));
    dev->report_len = (len > 0 && len < (long)sizeof(dev->report)) ? len : 0;
}
```

`veille_report_text` (`core/src/report.c`) est le **même** code que celui du jumeau Python du chapitre 2 : le format est donc vérifié octet pour octet par le différentiel.

Le résultat réel, lu sur la cible (`preuve/qnx80/e4-retour-signal-20261112T204646Z.log`) :

```
VERDICT_SILENCE:
WARN   VEILLE_TECHNICAL_ALARM  chain=/dev/veille  stage=acquire  state=sensor_dead|bus_ok|prio_normal|alarm_none  bound=50  latency=15
OK
VERDICT_SIGNAL:
INFO   VEILLE_OK  chain=/dev/veille  stage=alarm  state=sensor_ok|bus_ok|prio_normal|alarm_none  bound=200
OK
```

Deux choses à remarquer :

- **La ligne d'alarme technique est à part** du verdict du capteur (`tech_kind` / `tech_v` dans `veille_dev_t`). Une alarme technique (perte de signal) ne **masque** pas l'état du patient, et l'état du patient n'efface pas l'alarme. Le `CONTRACT.md` §6.1 accepte plusieurs verdicts par rapport, séparés par `\n`.
- **`bound=200` et `bound=50`** sont les bornes gelées du `CONTRACT.md` §3 (`bound_alarm_ms = 200`, `bound_tech_ms = 50`), reprises telles quelles par `veille_pipe_default_config`.

### (c) Le client : `O_CREAT` sur un périphérique

Dernier piège, côté client cette fois. Le client Python ouvrait :

```c
/* version FAUSSE — host/veille/resmgr_client.py (git 5c2e18d) */
descripteur = os.open(chemin, os.O_WRONLY | os.O_CREAT, 0o644)
```

Sur un **périphérique**, `O_CREAT` n'a pas de sens : le resource manager refuse la création et renvoie `EINVAL`. La version corrigée :

```python
# version CORRECTE — host/veille/resmgr_client.py (HEAD)
def _ouvrir_sortie(chemin):
    """Ouvre la destination en écriture (fichier tronqué, périphérique QNX intact).

    Sur un périphérique (`/dev/veille`), `O_CREAT`/`O_TRUNC` n'ont pas de sens et
    le resource manager les refuse (EINVAL) : si le chemin existe déjà, on ouvre
    en écriture seule.
    """
    if os.path.exists(chemin):
        if os.path.isfile(chemin):
            os.truncate(chemin, 0)
        descripteur = os.open(chemin, os.O_WRONLY)
    else:
        descripteur = os.open(chemin, os.O_WRONLY | os.O_CREAT, 0o644)
    # buffering=1 : une ligne = un write() → un échantillon par écriture,
    # ce qui préserve la cadence réelle et l'horodatage côté serveur.
    return os.fdopen(descripteur, "w", encoding="utf-8", buffering=1)
```

Le même programme sert à écrire dans un fichier (hôte, tests) et dans `/dev/veille` (cible) : `O_CREAT` seulement si le chemin **n'existe pas**. Et `buffering=1` (line-buffered) garantit **une ligne = un `write()`** : l'horodatage serveur est donc celui de l'échantillon, pas celui du flush du tampon.
## 5.8 Mesurer ce que vit le client

L'aller-retour d'une écriture se mesure côté client, avec un horodatage monotone de part et d'autre (`tools/qnx/bench_client.c`) :

```c
    for (int i = 0; i < n_samples; i++) {
        char ligne[32];
        int len = snprintf(ligne, sizeof(ligne), "bpm %d\n", (i % 2) ? bpm + 2 : bpm);
        long t0 = now_us();
        int w = write(fd, ligne, (size_t)len);
        long t1 = now_us();
        if (w != len) { perror("[client] write"); break; }
        long dt = t1 - t0;
        printf("rtt_us=%ld\n", dt);
```

Le `write()` étant un `MsgSend`, il ne rend la main qu'**après** la réponse du rm : `dt` est l'**aller-retour réel**, qui inclut la file d'attente du dispatch, le traitement de la chaîne et le retour noyau.

> ⚠️ `bpm` et `bpm + 2` en alternance : c'est pour ne pas déclencher la détection « capteur figé » de la chaîne (deux valeurs **identiques** consécutives = capteur figé, cf. `target/pipe/veille_pipe.c`, `veille_pipe_push`).

Les deux mesures sont **croisées** dans le rapport de preuve (`docs/QNX-EVIDENCE.md` §6) : côté client (`rtt_us`), p50 **35 µs** / p99 **200 µs** / max **5 250 µs** au repos ; côté serveur (`lat_write_max_us`), max **3 µs**. L'écart n'est pas du traitement : c'est **l'attente** du message dans le dispatch. C'est exactement ce que le chapitre 6 va mesurer et expliquer.

## 5.9 Exercice « à toi » : ajouter une métrique et un nœud `/dev/veille/stats`

**Énoncé.** Le serveur publie aujourd'hui le verdict sur `/dev/veille` (offset 0) et les mesures internes sur un **offset réservé** (`VEILLE_STATS_OFFSET`). On veut un **deuxième nœud** : `/dev/veille/stats`, lisible directement (`cat /dev/veille/stats`), qui affiche le nombre d'échantillons reçus et le nombre d'alarmes techniques émises.

**Contraintes** (elles sont dans le contrat du projet, pas négociables) :

1. Le format du `CONTRACT.md` §6.1 (verdict au format texte) **ne doit pas changer** : ni ligne, ni clé, ni ordre.
2. Chaque fichier écrit ou modifié fait **moins de 500 lignes**, chaque fonction **moins de 50 lignes**.
3. Zéro duplication : si le texte des mesures existe déjà (`veille_rm_stats_text`), on ne le réécrit pas.

**Le point de départ** — le handler `open` déjà écrit en §5.2 (`target/rm/rm_io.c`) : il décide, à l'ouverture, quel nœud le client a ouvert ; c'est là qu'on distingue `/dev/veille` de `/dev/veille/stats`.

**Pistes** (l'exercice est ouvert, il y a plusieurs réponses correctes) :

- `io_open_t` porte le chemin demandé (`msg->path`) : on peut comparer à `"/dev/veille/stats"` dans le handler `open`, et mémoriser le choix dans l'OCB (par exemple via `ocb->offset` mis à un marqueur, ou un attribut de `veille_dev_t`).
- Un `devctl` est l'autre option idiomatique — `iofunc_devctl_default` renvoie `ENOSYS` tant que vous ne le remplacez pas.
- Comptez les alarmes techniques : `veille_rm_set_tech` (`target/rm/rm_chain.c`) est **le** point de passage de toutes les alarmes techniques — c'est là qu'un compteur se pose, sans duplication.
- Réutilisez `veille_rm_stats_text()` : il rend déjà `n_samples`, `wd_count`, `wd_fired`, `prio_base`… au format `cle=valeur`.

**Résultat attendu** (sur la cible, après un passage de `bench_client samples`) :

```
$ ./veille-rm &
$ ./bench_client samples --n 10 --prio 40 --label moi
# label=moi prio=40 n=10 interval_us=0 bpm=72
rtt_us=13
…
$ cat /dev/veille/stats
n_samples=10
n_alarms_tech=0
…
```

Et le **critère de réussite** :

- `cat /dev/veille` reste **strictement identique** avant et après votre modification (une ligne de plus ou un ordre de clés différent = échec) ;
- `/dev/veille/stats` et l'offset réservé rendent la **même information** (pas deux implémentations du même compteur) ;
- le compteur d'alarmes techniques doit être **non nul** quand on provoque une panne : envoyez `bpm -1` (capteur mort) ou deux `bpm 72` identiques (capteur figé) et vérifiez que le verdict passe à `WARN VEILLE_TECHNICAL_ALARM` **et** que le compteur s'incrémente.

> 💡 Le vrai test de votre exercice : relisez `docs/QNX-EVIDENCE.md` §4. Les défauts 3 et 8 (« une seule valeur par écriture », « une alarme technique masquait le verdict ») sont exactement de ce type : **un état partagé mal tenu**. Un compteur d'alarmes techniques mal câblé reproduce le défaut 8 exactement.

## 5.10 Ce que vous avez maintenant

- Un **resource manager** QNX 8.0 qui publie `/dev/veille` : `dispatch_create` → `resmgr_attach` → boucle `dispatch_block` / `dispatch_handler`.
- Le **pattern correct** de `io_write` (`_IO_SET_WRITE_NBYTES` puis `return EOK`) et de `io_read` (`SETIOV` + `_RESMGR_NPARTS(1)`), avec le code d'erreur exact que le client recevait quand on s trompait.
- La lecture des données par `resmgr_msgget` (pas de copie contiguë supposée).
- La gestion des **écritures en lot** (jusqu'à 256 échantillons, rejet total si une ligne est invalide).
- Un verdict rendu au **format texte du CONTRAT**, horodaté **côté serveur**, par le code pur `core/src/report.c`.

Le chapitre suivant prend ce resource manager et pose la question qui compte : **qu'est-ce que le noyau garantit, et comment on le mesure ?**

← [Chapitre 4 : Porter sur QNX 8.0](04-porter-sur-qnx.md) · [Chapitre 6 : Protéger sa chaîne sur QNX 8.0](06-proteger-sa-chaine-qnx.md) · [Sommaire](README.md)
