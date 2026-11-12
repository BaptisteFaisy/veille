#ifndef VEILLE_REPORT_H
#define VEILLE_REPORT_H

#include "veille/verdict.h"
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

/* §5.4 du CONTRAT — fourni par l'appelant ; core/ ne lit ni horloge ni fichier. */
typedef struct {
    const char *config_file;
    const char *config_sha256;   /* 64 hex */
    const char *timestamp_utc;   /* ISO-8601 */
    const char *veille_version;
} veille_report_meta;

/* Sémantique : octets qui auraient été écrits tampon plein (comme snprintf) ;
 * <0 si argument invalide ; NUL-terminé si cap>0. */
long veille_report_text    (const veille_verdict *v, size_t n, char *buf, size_t cap);
long veille_report_json    (const veille_verdict *v, size_t n, char *buf, size_t cap);
long veille_report_markdown(const veille_verdict *v, size_t n,
                            const veille_report_meta *meta, char *buf, size_t cap);
int  veille_report_exit_code(const veille_verdict *v, size_t n);  /* 0 si aucun error */

#ifdef __cplusplus
}
#endif
#endif /* VEILLE_REPORT_H */
