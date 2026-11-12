#ifndef VEILLE_PORT_TIME_H
#define VEILLE_PORT_TIME_H

#ifdef __cplusplus
extern "C" {
#endif

/* Couche port — horloge monotone.
 * core/ est pur (ni horloge ni fichier) : c'est la couche cible qui horodate.
 * Une seule déclaration, deux implémentations isolées (zéro #ifdef dispersé) :
 *   - target/port/host_time.c : hôte Linux (gcc, make sim/demo/test)
 *   - target/port/qnx_time.c  : cible QNX 8.0 (qcc, make qnx)
 */
long veille_now_us(void);   /* horloge monotone en microsecondes */

#ifdef __cplusplus
}
#endif
#endif /* VEILLE_PORT_TIME_H */
