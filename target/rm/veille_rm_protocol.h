#ifndef VEILLE_RM_PROTOCOL_H
#define VEILLE_RM_PROTOCOL_H

/* Veille — protocole d'échange entre /dev/veille et ses clients.
 *
 * Constantes partagées entre le resource manager (target/rm/) et les clients
 * de mesure (tools/qnx/) : une seule définition, pas de duplication.
 *
 *   - VEILLE_MOUNT_POINT : chemin du nœud de device.
 *   - VEILLE_STATS_OFFSET : offset read() réservé au canal de mesures
 *     (statistiques E2/E3/E4/H2) rendu sous forme de texte « cle=valeur ».
 *     Le format texte (et non un binaire) est choisi pour que les journaux
 *     de preuve soient lisibles et rejouables sans outil spécifique.
 */
#define VEILLE_MOUNT_POINT    "/dev/veille"
#define VEILLE_STATS_OFFSET   0x40000000L      /* offset read() réservé au canal de mesures */

#endif /* VEILLE_RM_PROTOCOL_H */
