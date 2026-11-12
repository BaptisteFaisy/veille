/* Veille — resource manager QNX 8.0 : handlers io_read / io_write (iofunc).
 *
 * Contrat d'accès à /dev/veille :
 *   write("bpm 132\n") ou write("132\n") → pousse un échantillon horodaté
 *       (négatif = capteur mort simulé) dans la chaîne ; le verdict est mis à jour.
 *   read() → renvoie le verdict courant au FORMAT TEXTE DU CONTRAT
 *       (core/report.c), avec sémantique de position (offset) et EOF.
 * Conventions de retour vérifiées dans les en-têtes du SDP 8.0 :
 *   sys/resmgr.h (_RESMGR_NPARTS, _RESMGR_STATUS), sys/iomsg.h (_IO_SET_*),
 *   sys/iofunc.h (iofunc_read_verify/iofunc_write_verify prennent io_*_t*). */
#include <errno.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#include "veille_rm.h"

int veille_io_read(resmgr_context_t *ctp, io_read_t *msg, RESMGR_OCB_T *ocb) {
    int status = iofunc_read_verify(ctp, msg, ocb, NULL);
    if (status != EOK) return status;
    if ((msg->i.xtype & _IO_XTYPE_MASK) != _IO_XTYPE_NONE) return ENOSYS;

    veille_dev_t *dev = (veille_dev_t *)ocb->attr;   /* attr = premier membre */
    long off = (long)ocb->offset;
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
