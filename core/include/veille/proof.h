#ifndef VEILLE_PROOF_H
#define VEILLE_PROOF_H

#include "veille/chain.h"
#include "veille/state.h"
#include "veille/verdict.h"
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

/* §7 du cahier — masque d'exploration : quelles dimensions énumérer */
typedef struct {
    unsigned explore_sensor : 1;
    unsigned explore_bus    : 1;
    unsigned explore_prio   : 1;
    unsigned explore_alarm  : 1;
    unsigned explore_stage  : 1;
} veille_fault_mask;

/* Explore exhaustivement les états de défaillance et prouve la borne (§7.3).
 * Retourne 0 si preuve complète (borne tenue partout), 1 si contre-exemple, <0 si erreur.
 * Remplit out[0..*n_out) : PROOF_COMPLETE ou COUNTEREXAMPLE + verdicts de détail. */
int veille_proof_explore(const veille_chain_config *cfg,
                         const veille_fault_mask *mask,
                         veille_verdict *out, size_t cap, size_t *n_out);

#ifdef __cplusplus
}
#endif
#endif /* VEILLE_PROOF_H */
