/* Veille — resource manager /dev/veille : handlers io_read / io_write.
 *
 * Contrat d'accès à /dev/veille :
 *   write("bpm 132\n") ou write("132\n") → pousse un échantillon horodaté
 *       (négatif = capteur mort simulé) dans la chaîne ; le verdict est mis à jour.
 *   read() à l'offset 0 → renvoie le verdict courant au FORMAT TEXTE DU CONTRAT
 *       (core/report.c), avec sémantique de position (offset) et EOF.
 *   read() à l'offset VEILLE_STATS_OFFSET → rend le canal de mesures
 *       (statistiques E2/E3/E4/H2) au format texte « cle=valeur ».
 *       Ce canal est réservé à l'outillage de preuve (tools/qnx/) : il ne
 *       modifie pas le verdict et ne pollue pas le contrat.
 * Conventions de retour vérifiées dans les en-têtes du SDP 8.0 :
 *   sys/resmgr.h (_RESMGR_NPARTS, _RESMGR_STATUS), sys/iomsg.h (_IO_SET_*),
 *   sys/iofunc.h (iofunc_read_verify/iofunc_write_verify prennent io_*_t*). */
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#include "veille_rm.h"

/* Ouverture : on compte les clients connectés. Le handler de disconnect
 * (CHANNEL) ne signale une mort que si un client était réellement connecté —
 * sinon la notification de démarrage empoisonnerait le verdict. */
int veille_open(resmgr_context_t *ctp, io_open_t *msg, RESMGR_HANDLE_T *handle, void *extra) {
    veille_dev_t *dev = (veille_dev_t *)handle;   /* attr = premier membre */
    int status = iofunc_open_default(ctp, msg, handle, extra);
    if (status == EOK) veille_rm_note_client(dev, 1);
    return status;
}

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

/* Analyze l'échantillon écrit : "bpm N" ou "N" ; retourne 1 si valide. */
static int parse_sample(const char *buf, long *bpm) {
    const char *p = buf;
    if (strncmp(p, "bpm", 3) == 0) p += 3;
    char *end;
    long v = strtol(p, &end, 10);
    if (end == p) return 0;
    *bpm = v;
    return 1;
}

/* Un write peut contenir PLUSIEURS échantillons (un client qui écrit en tampon,
 * ex. Python, envoie des paquets de lignes). On les parse tous : toute ligne
 * invalide rejette l'écriture entière (EINVAL), aucune moitié n'est poussée. */
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

int veille_io_write(resmgr_context_t *ctp, io_write_t *msg, RESMGR_OCB_T *ocb) {
    int status = iofunc_write_verify(ctp, msg, ocb, NULL);
    if (status != EOK) return status;
    int xtype = msg->i.xtype & _IO_XTYPE_MASK;
    if (xtype != _IO_XTYPE_NONE) return ENOSYS;

    size_t nb = _IO_WRITE_GET_NBYTES(msg);
    if (nb == 0 || nb >= VEILLE_WRITE_CAP) return EINVAL;

    /* Les données ne sont PAS forcément contiguës à l'en-tête : on les lit par
     * resmgr_msgget (pattern officiel du SDP, s1_resmgr_write_simple). */
    char buf[VEILLE_WRITE_CAP];
    if (resmgr_msgget(ctp, buf, nb, sizeof(msg->i)) == -1) return errno;
    buf[nb] = '\0';

    long valeurs[VEILLE_BATCH_MAX];
    int n = parse_lot(buf, valeurs, VEILLE_BATCH_MAX);
    if (n < 0) return -n;

    veille_dev_t *dev = (veille_dev_t *)ocb->attr;   /* attr = premier membre */
    /* E2 : on relève la priorité effective AVANT tout traitement : c'est la
     * priorité que le noyau a accordée au fil (héritage) à la réception. */
    veille_rm_prio_observed(dev);
    if (dev->no_inherit) veille_rm_prio_drop(dev);   /* témoin E2 : on annule */
    for (int i = 0; i < n; i++) veille_rm_push(dev, valeurs[i]);  /* horodaté serveur */

    ocb->attr->flags |= IOFUNC_ATTR_MTIME | IOFUNC_ATTR_DIRTY_TIME;
    ocb->offset += nb;
    _IO_SET_WRITE_NBYTES(ctp, nb);   /* pose ctp->status ; ne PAS le retourner */
    return EOK;                      /* retour positif = errno côté client */
}

/* --- Canal de mesures : texte « cle=valeur » ------------------------------
 * Format texte (et non binaire) : les journaux de preuve restent lisibles et
 * analysables avec n'importe quel outil (awk, python, grep). */
static size_t stats_put(char *buf, size_t cap, size_t off, const char *key, long val) {
    int w = snprintf(buf + off, cap - off, "%s=%ld\n", key, val);
    if (w < 0 || (size_t)w >= cap - off) return cap - 1;
    return off + (size_t)w;
}

static size_t stats_hist(char *buf, size_t cap, size_t off, const char *key,
                         const unsigned long *h, int n) {
    int w = snprintf(buf + off, cap - off, "%s=", key);
    if (w < 0 || (size_t)w >= cap - off) return cap - 1;
    off += (size_t)w;
    for (int i = 0; i < n; i++) {
        w = snprintf(buf + off, cap - off, "%s%lu", i ? "," : "", h[i]);
        if (w < 0 || (size_t)w >= cap - off) return cap - 1;
        off += (size_t)w;
    }
    if (off < cap - 1) { buf[off++] = '\n'; buf[off] = '\0'; }
    return off;
}

static size_t stats_core(const veille_dev_t *dev, char *buf, size_t cap, size_t off) {
    int w = snprintf(buf + off, cap - off, "# veille-rm mesures v1\n");
    if (w < 0 || (size_t)w >= cap - off) return cap - 1;
    off += (size_t)w;
    off = stats_put(buf, cap, off, "prio_base", dev->prio_base);      /* E2 */
    off = stats_put(buf, cap, off, "prio_effective", dev->prio_effective);
    off = stats_put(buf, cap, off, "prio_dropped", dev->prio_dropped);
    off = stats_put(buf, cap, off, "prio_after_drop", dev->prio_after_drop);
    off = stats_put(buf, cap, off, "n_samples", dev->n_samples);
    off = stats_put(buf, cap, off, "n_clients", dev->n_clients);
    off = stats_put(buf, cap, off, "n_opens", dev->n_opens);
    off = stats_put(buf, cap, off, "n_disconnects", dev->n_disconnects);
    off = stats_put(buf, cap, off, "wd_ms", dev->wd_ms);              /* E4 */
    off = stats_put(buf, cap, off, "wd_count", dev->wd_count);
    off = stats_put(buf, cap, off, "wd_fired", dev->wd_fired);
    off = stats_put(buf, cap, off, "wd_silence_ms", dev->wd_silence_ms);
    off = stats_put(buf, cap, off, "uptime_us", dev->uptime_us);      /* E3 */
    off = stats_put(buf, cap, off, "ticks", dev->n_ticks);            /* E3 */
    off = stats_put(buf, cap, off, "tick_period_us", dev->tick_period_us);
    off = stats_put(buf, cap, off, "tick_min_us", dev->tick_min_us);
    off = stats_put(buf, cap, off, "tick_max_us", dev->tick_max_us);
    off = stats_put(buf, cap, off, "tick_sum_us", dev->tick_sum_us);
    off = stats_put(buf, cap, off, "tick_maxdev_us", dev->tick_maxdev_us);
    off = stats_put(buf, cap, off, "tick_coalesced", dev->tick_coalesced);
    long ppm = dev->tick_period_us
             ? (dev->tick_maxdev_us * 1000000L) / dev->tick_period_us : 0;
    off = stats_put(buf, cap, off, "tick_maxdev_ppm", ppm);
    off = stats_put(buf, cap, off, "lat_tick_n", dev->lat_tick_n);    /* H2 */
    off = stats_put(buf, cap, off, "lat_tick_max_us", dev->lat_tick_max_us);
    off = stats_put(buf, cap, off, "lat_tick_sum_us", dev->lat_tick_sum_us);
    off = stats_put(buf, cap, off, "lat_write_n", dev->lat_write_n);
    off = stats_put(buf, cap, off, "lat_write_max_us", dev->lat_write_max_us);
    off = stats_put(buf, cap, off, "lat_write_sum_us", dev->lat_write_sum_us);
    off = stats_put(buf, cap, off, "bound_alarm_ms", dev->cfg.bound_alarm_ms);
    off = stats_put(buf, cap, off, "bound_tech_ms", dev->cfg.bound_tech_ms);
    return off;
}

void veille_rm_stats_text(const veille_dev_t *dev, char *buf, size_t cap) {
    if (!buf || cap == 0) return;
    size_t off = 0;
    buf[0] = '\0';
    off = stats_core(dev, buf, cap, off);
    off = stats_hist(buf, cap, off, "prio_hist", dev->prio_hist, VEILLE_PRIO_HIST_MAX);
    off = stats_hist(buf, cap, off, "tick_hist", dev->tick_hist, VEILLE_TICK_BUCKETS);
    off = stats_hist(buf, cap, off, "lat_tick_hist", dev->lat_tick_hist, VEILLE_LAT_BUCKETS);
    off = stats_hist(buf, cap, off, "lat_write_hist", dev->lat_write_hist, VEILLE_LAT_BUCKETS);
    buf[cap - 1] = '\0';
}