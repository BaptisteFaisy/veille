# Veille — CONTRAT (gelé)

Version 0.2 — 12 novembre 2026. Ce fichier est la **source de vérité** du socle.
Toute divergence se règle en modifiant ce fichier, jamais en dupliquant la logique
ailleurs. Le cahier des charges (`VEILLE-cahier-des-charges.md`) donne le contexte ;
ce contrat précise les formats de façon **octet pour octet** afin que le cœur C et
le jumeau Python soient comparables par différentiel.

---

## 1. Chaîne de traitement (figée)

```
sample(t0) → acquire(t1) → filter(t2) → decide(t3) → alarm(t4) → acknowledge(t5)
```

- Latence de bout en bout : `L = t4 - t0` (déclenchement de l'alarme).
- Latence d'acquittement : `A = t5 - t4`.
- Aucune étape ne remonte : un étage ne relit jamais l'échantillon brut. Toute erreur
  arrête la chaîne et produit un verdict `VEILLE_CHAIN_FAULT` avec l'étage fautif —
  **jamais** de reprise approximative sur un échantillon partiellement traité.
- Chaque étage porte un timestamp monotone **fourni par l'appelant** ; `core/` ne lit
  aucune horloge.

## 2. Architecture et portabilité

- `core/` : C11 **pur** — ni horloge, ni fichier, ni socket, ni état global mutable.
  L'appelant fournit les échantillons, les timestamps et les tampons ; le cœur n'alloue
  que ce que l'appelant lui passe. Compilé en `-std=c11 -O2 -Wall -Wextra -Werror`.
- `host/` : Python 3 **standard uniquement** (aucune dépendance à installer). C'est un
  **jumeau de vérification indépendant**, pas une copie du C : même contrat de sortie,
  implémentation séparée. Le désaccord C↔Python est un bug, réduit dichotomiquement.
- `target/` : code QNX 8.0 (resource manager `/dev/veille`, capteurs simulés, alarme,
  capture kernel trace). Ne bloque aucune exigence S : le socle tourne sans QNX.

## 3. Bornes (configurables — défaut à geler, §10 E1 du cahier)

| Priorité | `B_alarm` | `B_ack` | Profil sonore |
|---|---|---|---|
| `VEILLE_PRIO_HIGH` | 100 ms | 60 s | 3 pulses rapides, pause |
| `VEILLE_PRIO_MEDIUM` | 500 ms | 120 s | 2 pulses, pause longue |
| `VEILLE_PRIO_LOW` | 1000 ms | 300 s | 1 pulse, pause très longue |
| technique | 50 ms | — | continu (défaillance système) |

La config porte aussi `bound_tech_ms` (borne de l'alarme technique, défaut 50) et
`tech_detect_ms` (latence pire-cas de détection d'une panne d'étage, défaut 15).
P2 est vérifiée globalement : s'il existe un état à chaîne rompue, alors
`tech_detect_ms ≤ bound_tech_ms` (décision D9).

**Espace d'états complet (mesuré, E5 validé)** : 5 capteur × 3 bus × 2 priorité ×
5 alarme × 32 masques d'étage = **4800 états**, explorés en < 10 ms.

Les bornes sont des **ordres de grandeur** publiquement documentés d'IEC 60601-1-8 ;
elles sont configurables (`veille_chain_config`) et doivent être gelées après lecture
page à page de la norme (essai E1).

## 4. Verdicts (§5.3 du cahier)

10 codes, dans cet ordre (enum `veille_verdict_code`, sentinelle `VEILLE_VERDICT__COUNT`) :

| # | Code | Sévérité par défaut | Porteur |
|---|---|---|---|
| 0 | `VEILLE_OK` | info | chain_id, latency_ms |
| 1 | `VEILLE_LATENCY_BOUND_EXCEEDED` | error | chain_id, bound_ms, latency_ms, stage, state |
| 2 | `VEILLE_ALARM_MISSED` | error | chain_id, threshold, state |
| 3 | `VEILLE_SENSOR_FAULT` | warning | sensor_id, fault_kind, state |
| 4 | `VEILLE_PRIORITY_INVERSION` | error | chain_id, holder_prio, waiter_prio |
| 5 | `VEILLE_TECHNICAL_ALARM` | warning | chain_id, stage, cause |
| 6 | `VEILLE_CHAIN_FAULT` | error | chain_id, stage, cause |
| 7 | `VEILLE_PROOF_COMPLETE` | info | states_explored, bound_ms, config_sha256 |
| 8 | `VEILLE_PROOF_COUNTEREXAMPLE` | error | states_explored, fault_state, bound_ms, latency_ms |
| 9 | `VEILLE_ACK_TIMEOUT` | warning | chain_id, ack_bound_ms, elapsed_ms |

Un verdict porte toujours : `code`, `sev`, `message`. Les champs `chain_id`, `sensor_id`,
`stage`, `state`, `bound_ms`, `latency_ms`, `threshold`, `holder_prio`, `waiter_prio`,
`states_explored`, `config_sha256`, `fault_state`, `ack_bound_ms`, `elapsed_ms` sont
**optionnels** (absents si non applicables / nuls / 0).

## 5. API C (en-têtes sous `core/include/veille/`)

`verdict.h` :
```c
typedef enum { /* §4, ordre figé */ } veille_verdict_code;
typedef enum { VEILLE_SEV_INFO, VEILLE_SEV_WARNING, VEILLE_SEV_ERROR } veille_severity;

const char *veille_verdict_name(veille_verdict_code code);   /* hors plage -> "VEILLE_UNKNOWN" */
const char *veille_severity_name(veille_severity sev);        /* "info"|"warning"|"error" */
veille_severity veille_verdict_default_severity(veille_verdict_code code);
int veille_verdict_code_valid(veille_verdict_code code);      /* 1 si dans [0,COUNT) */
```

`chain.h` :
```c
typedef enum { VEILLE_STAGE_ACQUIRE, VEILLE_STAGE_FILTER,
               VEILLE_STAGE_DECIDE, VEILLE_STAGE_ALARM,
               VEILLE_STAGE_ACK, VEILLE_STAGE__COUNT } veille_stage;

typedef enum { VEILLE_PRIO_HIGH, VEILLE_PRIO_MEDIUM, VEILLE_PRIO_LOW,
               VEILLE_PRIO_TECHNICAL, VEILLE_PRIO__COUNT } veille_priority;

typedef struct {
    veille_priority priority;
    long bound_alarm_ms;                          /* B_alarm */
    long bound_ack_ms;                            /* B_ack */
    long bound_tech_ms;                           /* B_tech — alarme technique (défaut 50) */
    long tech_detect_ms;                          /* latence pire-cas de détection de panne */
    long stage_latency_ms[VEILLE_STAGE__COUNT];   /* latence pire-cas par étage */
} veille_chain_config;

const char *veille_stage_name(veille_stage s);
const char *veille_priority_name(veille_priority p);
long veille_chain_latency_ms(const veille_chain_config *cfg); /* somme des étages */
```

`state.h` :
```c
typedef enum { VEILLE_SENSOR_OK, VEILLE_SENSOR_STUCK, VEILLE_SENSOR_DEAD,
               VEILLE_SENSOR_NOISY, VEILLE_SENSOR_DRIFT, VEILLE_SENSOR__COUNT } veille_sensor_state;
typedef enum { VEILLE_BUS_OK, VEILLE_BUS_SATURATED, VEILLE_BUS_SPIKE,
               VEILLE_BUS__COUNT } veille_bus_state;
typedef enum { VEILLE_PRIO_NORMAL, VEILLE_PRIO_INVERTED, VEILLE_PRIO_MODE__COUNT } veille_prio_mode;
typedef enum { VEILLE_ALARM_NONE, VEILLE_ALARM_SINGLE, VEILLE_ALARM_CONCURRENT,
               VEILLE_ALARM_LOCKED, VEILLE_ALARM_ACKED, VEILLE_ALARM__COUNT } veille_alarm_state;

typedef struct {
    veille_sensor_state sensor;
    veille_bus_state    bus;
    veille_prio_mode    prio;
    veille_alarm_state  alarm;
    unsigned            stage_fault_mask; /* bit i = étage i en panne */
} veille_fault_state;

/* Latence pire-cas de la chaîne dans cet état (ms). Retourne <0 si chaîne rompue. */
long veille_state_worst_latency_ms(const veille_chain_config *cfg, const veille_fault_state *st);
int  veille_state_chain_broken(const veille_fault_state *st); /* 1 si un étage critique est en panne */
```

`proof.h` :
```c
typedef struct {
    unsigned explore_sensor : 1;
    unsigned explore_bus    : 1;
    unsigned explore_prio   : 1;
    unsigned explore_alarm  : 1;
    unsigned explore_stage  : 1;
} veille_fault_mask;

/* Explore exhaustivement les états de défaillance et prouve la borne.
 * Retourne 0 si preuve complète, 1 si contre-exemple, <0 si erreur.
 * Remplit out[0..*n_out) avec les verdicts (PROOF_COMPLETE ou COUNTEREXAMPLE + détails). */
int veille_proof_explore(const veille_chain_config *cfg,
                         const veille_fault_mask *mask,
                         veille_verdict *out, size_t cap, size_t *n_out);
```

`report.h` :
```c
typedef struct {
    const char *config_file;
    const char *config_sha256;   /* 64 hex */
    const char *timestamp_utc;   /* ISO-8601 */
    const char *veille_version;
} veille_report_meta;

long veille_report_text    (const veille_verdict *v, size_t n, char *buf, size_t cap);
long veille_report_json    (const veille_verdict *v, size_t n, char *buf, size_t cap);
long veille_report_markdown(const veille_verdict *v, size_t n,
                            const veille_report_meta *meta, char *buf, size_t cap);
int  veille_report_exit_code(const veille_verdict *v, size_t n);
```
Sémantique de retour : nombre d'octets qui auraient été écrits tampon plein (comme
`snprintf`) ; `< 0` si argument invalide. Contenu toujours NUL-terminé si `cap > 0`.
Tout champ NULL de `veille_report_meta` est rendu `inconnu`.

## 6. Formats de sortie

### 6.1 Texte (`veille_report_text`)
Une ligne par verdict, préfixe de sévérité, puis code et détails :
```
ERROR  VEILLE_LATENCY_BOUND_EXCEEDED  chain=ecg_high  bound=100ms  latency=142ms  stage=decide  state=sensor_stuck|bus_saturated
WARN   VEILLE_TECHNICAL_ALARM  chain=spo2_med  stage=acquire  cause=sensor_dead
INFO   VEILLE_PROOF_COMPLETE  states=18432  bound=100ms  config_sha256=a3f9...
```
Format exact d'une ligne (séparateurs = **2 espaces**) :
`<PRÉFIXE><CODE>  <DÉTAILS>`
- `<PRÉFIXE>` = label de sévérité (`ERROR`/`WARN`/`INFO`) aligné à gauche sur
  **5 caractères** puis **2 espaces** (champ de 7) : `ERROR  `, `WARN   `, `INFO   `.
- `<CODE>` = nom canonique du verdict.
- `<DÉTAILS>` : paires `clé=valeur` séparées par 2 espaces, dans l'ordre figé :
  `chain`, `sensor`, `stage`, `state`, `bound`, `latency`, `threshold`, `cause`,
  `states`, `config_sha256`, `holder_prio`, `waiter_prio`, `ack_bound`, `elapsed`.
  Les clés absentes sont omises. `state` = noms d'états joints par `|`.
Termine par `OK` si aucun verdict error, sinon `FAILED <n> error(s)`. Lignes jointes
par `\n`, avec un `\n` final.

### 6.2 JSON (`veille_report_json`) — **une ligne par verdict**, compact
Ordre des clés **figé** : `code`, `sev`, `chain_id`, `sensor_id`, `stage`, `state`,
`bound_ms`, `latency_ms`, `threshold`, `holder_prio`, `waiter_prio`, `states_explored`,
`config_sha256`, `ack_bound_ms`, `elapsed_ms`, `message`. Clés optionnelles **omises**
quand le champ est absent (NULL / 0). `message` toujours présent. Séparateurs `,` et `:`
**sans espace**. Équivalent Python : `json.dumps(obj, separators=(',', ':'), ensure_ascii=False)`.

Échappement (identique C et Python) : `"` → `\"`, `\` → `\\`, `\b \f \n \r \t` → escape
court, tout autre caractère de contrôle `< 0x20` → `\u00XX` (hex **minuscule**). Les
octets UTF-8 ≥ 0x20 passent tels quels.

### 6.3 Markdown d'audit (`veille_report_markdown`) — §5.5 du cahier
Structure figée :
```
# Rapport de preuve de latence — Veille

- Configuration : <config_file>
- Empreinte SHA-256 : <config_sha256|inconnu>
- Horodatage (UTC) : <timestamp_utc|inconnu>
- Version de Veille : <veille_version|inconnu>

## Synthèse
<OK | FAILED n error(s)>

## Propriétés vérifiées
### P1 — Latence d'alarme ≤ <bound> ms
- Méthode : exploration exhaustive de <states> états de défaillance
- Résultat : <borne tenue | contre-exemple>
- Contre-exemple : <état, latence, étage> (si applicable)
```

## 7. Invariants

- `core/` est déterministe : mêmes entrées → exactement mêmes sorties, octet pour octet.
- Aucun appel à `malloc`/`free` dans `core/` hors de ce que l'appelant fournit.
- Aucune lecture d'horloge, de fichier, de socket, de variable d'environnement dans `core/`.
- Le jumeau Python (`host/`) produit des sorties **identiques** au C sur le même corpus.
- Tout fichier < 500 lignes, toute fonction < 50 lignes (garde CI).

---

*Contrat gelé v0.1 — toute modification passe par ce fichier.*
