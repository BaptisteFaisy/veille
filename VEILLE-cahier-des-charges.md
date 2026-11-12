# Veille — moniteur patient à latence d'alarme bornée et prouvée sur QNX 8.0

**Nom de travail : « Veille »** (le moniteur qui veille : la chaîne capteur→alarme tient sa borne, et le prouve).
Version 0.1 — 12 novembre 2026 — projet candidat au QNX Global Hackathon, catégorie **Robotics & Medical**.
Visé explicitement : **Best of Robotics & Medical**, bonus **Best use of QNX-specific Technologies** (message passing, priority inheritance, resource managers, pulses/timers, kernel trace y sont nommément cités) et **Best Codelab/Tutorial**.

> Note de nommage : « Veille » est un nom commun français, aucune marque de tiers. Le règlement proscrit les marques de tiers dans les supports de soumission (vidéo comprise) — aucun nom de produit médical réel n'apparaît dans les supports.

---

## 0. Lecture rapide

**Ce que c'est.** Un moniteur patient QNX 8.0 où la chaîne **acquisition (ECG/SpO2/PA) → filtrage → décision → alarme audible** a une **latence de bout en bout bornée**, et où cette borne est **prouvée par exploration exhaustive de tous les états de défaillance** au lieu d'être mesurée sur quelques scénarios chanceux.

**La promesse, en une phrase.** Une alarme médicale passe d'« elle a sonné en test » à « **sa latence est garantie dans la borne B dans chaque état atteignable du système**, avec un certificat exploitable dans un dossier IEC 62304 ».

**Trois idées qui portent le projet.**

1. **L'alarme est un chemin critique à deadline, pas une fonctionnalité.** Comme Ambre traite l'écriture du crash comme une deadline de 20 ms, Veille traite la chaîne capteur→alarme comme un chemin à deadline garantie (ex. 100 ms pour une priorité haute). Le déterminisme QNX — priority inheritance à travers `MsgSend`, pulses et timers noyau, microkernel qui prévient de la mort d'un pair — est exactement ce qui rend la borne atteignable et vérifiable.
2. **La preuve par exploration exhaustive, pas par mesure.** Comme Ambre explore tous les états de coupure d'alimentation, Veille explore **tous les états de défaillance** de la chaîne (capteur bloqué/mort/bruité, bus saturé, inversion de priorité, alarmes concurrentes, panne d'un étage) et prouve que la latence reste dans la borne **dans chaque état**, ou qu'une alarme technique se déclenche dans sa propre borne. C'est la différence entre « ça a marché » et « c'est garanti ».
3. **IEC 60601-1-8 outillé, pas subi.** La norme exige des caractéristiques d'alarme (priorités haute/moyenne/basse, délais de déclenchement, profils sonores, verrouillage, acquittement, alarmes techniques). Veille fournit un framework qui **implémente et prouve** ces caractéristiques sur QNX, avec un rapport d'audit horodaté et empreinté (SHA-256 de la configuration) pour le dossier IEC 62304.

**Trois niveaux d'ambition.** **S** (socle : chaîne + jumeau + exploration d'un sous-ensemble d'états + rapport), **C** (complet : exploration exhaustive, fault injection, resource manager `/dev/veille`, kernel trace comme preuve, codelab), **X** (extrême : preuve formelle assistée, intégration matériel réel, dossier IEC 62304 complet).

**À valider avant d'écrire la moindre ligne de produit** (section 10) : cinq essais, dont E1 — geler les bornes et priorités exactes d'IEC 60601-1-8 — et E2 — confirmer que la priority inheritance `MsgSend` est observable par kernel trace sur QEMU.

**Statut des affirmations.** Section 13 : les valeurs exactes de délais d'IEC 60601-1-8 n'ont **pas** encore été lues page à page dans la norme (document payant). Les bornes utilisées sont des ordres de grandeur documentés publiquement ; c'est le premier travail de validation, pas une hypothèse de plus.

---

## 1. Contexte et cas d'usage

### 1.1 Qui a ce problème

| Acteur | Besoin | Ce qu'il fait aujourd'hui |
|---|---|---|
| Fabricant de moniteurs patient (IEC 60601-1-8, IEC 62304) | Prouver que l'alarme sonne dans le délai requis, dans tous les cas | Tests sur scénarios nominaux, argumentaire prose, tableur de cas |
| Intégrateur système médical sur QNX | Garantir la latence de bout en bout capteur→alarme | Mesures ponctuelles au System Profiler, sans borne prouvée |
| Responsable sûreté de fonctionnement | Montrer que la défaillance d'un capteur ne rate pas une alarme | Analyse FMEA manuelle, revue de code |
| Auditeur IEC 62304 | Vérifier que les exigences temporelles d'alarme sont couvertes et testées | Inspection de rapports de tests non exhaustifs |
| Développeur QNX médical | Comprendre pourquoi une alarme a été retardée sous charge | Essai-erreur, traces kernel relues à la main |

### 1.2 Pourquoi c'est un vrai marché

QNX équipe déjà des dispositifs médicaux (la documentation cite les medical devices parmi les systèmes critiques). IEC 60601-1-8 impose des caractéristiques temporelles d'alarme ; IEC 62304 impose de les prouver. Or **rien dans QNX SDP 8.0 n'outille cette preuve** : le System Profiler mesure, il ne prouve pas de borne dans le pire cas ; il n'existe ni framework d'alarme médicale, ni explorateur d'états de défaillance, ni générateur de certificat de latence. Veille occupe exactement cet espace — comme Tamis occupe l'analyse statique des politiques, comme Ambre occupe la durabilité prouvée du crash.

### 1.3 Ce que Veille n'est pas

Ni un moniteur patient complet certifié (hors périmètre : pas de certification réelle, pas de matériel médical réel), ni un analyseur de signal médical (pas de diagnostic, pas d'algorithme clinique), ni un système d'archivage de données patient (pas de DSE), ni un outil de développement générique. Veille est un **framework de garantie et de preuve de latence d'alarme** sur QNX.

---

## 2. Ancrage documentaire

### 2.1 Ce que QNX fournit déjà (à ne pas réinventer)

| Élément | Rôle pour Veille |
|---|---|
| Priority inheritance à travers `MsgSend` | La voie critique capteur→alarme ne peut pas être préemptée par du travail de moindre priorité |
| Pulses et timers noyau (`timer_create`, `MsgSendPulse`) | Cadence périodique d'acquisition et deadlines sans `sleep()` |
| Resource managers (`resmgr_*`) | `/dev/veille` : un processus possède la chaîne, les autres y accèdent par API typée |
| Microkernel isolation + `CHANNEL` disconnect | La mort d'un étage est notifiée aux pairs : décision→alarme sait que l'acquisition est tombée |
| Kernel trace (`tracelogger`, `traceprinter`) | Capture des événements message-passing/scheduling : la latence mesurée est la preuve empirique |
| System Profiler (Momentics) | Visualisation des latences — mais **mesure ponctuelle, pas de borne prouvée** |
| Adaptive partitioning | Isolation de la partition critique (alarme) vs best-effort (UI, réseau) |
| Power-Safe file system | Journal d'alarmes durable (comme Ambre) |
| `secpol` (politiques de sécurité) | Cloisonnement des processus de la chaîne (complément Tamis) |

### 2.2 Les trous exploités (à sourcer page à page — section 13)

| Code | Trou, tel que formulé | Source |
|---|---|---|
| M1 | **Aucun framework d'alarme médicale** : QNX ne fournit ni priorités d'alarme IEC 60601-1-8, ni profils sonores, ni verrouillage/acquittement | Inventaire QNX SDP 8.0 |
| M2 | **La latence de bout en bout n'est pas prouvée** : le System Profiler mesure des échantillons, il n'explore pas les états de défaillance ni ne certifie une borne pire-cas | `system_profiler` doc |
| M3 | **Pas d'exploration exhaustive d'états** pour les chaînes temps réel : rien n'énumère capteur bloqué/mort/bruité × bus saturé × inversion de priorité × alarmes concurrentes | Inventaire |
| M4 | **IEC 60601-1-8 non outillé** : les caractéristiques d'alarme (délais, priorités, sons) sont à implémenter à la main, sans support ni test de conformité | Norme externe |
| M5 | **Pas de certificat de latence exploitable en IEC 62304** : aucun générateur de rapport d'audit horodaté/empreinté pour les exigences temporelles | Inventaire |
| M6 | **La défaillance de capteur ne déclenche pas d'alarme technique bornée** : pas de supervision de la chaîne elle-même (capteur mort = silence, pas alarme) | IEC 60601-1-8 §alarmes techniques |

> Honnêteté : M1–M6 sont des affirmations sur l'**absence** d'outillage dans la documentation publique QNX 8.0. Comme pour Tamis, elles doivent être vérifiées page à page dans le SDP installé avant d'être gravées. Section 13.

---

## 3. Périmètre

### 3.1 Dans le périmètre

- **Chaîne d'alarme** : `échantillon capteur → acquire → filter → decide → alarm → acknowledge`, chaque étage horodaté.
- **Bornes de latence par priorité** : haute / moyenne / basse (IEC 60601-1-8), configurables, avec deadline de bout en bout.
- **Exploration exhaustive d'états** : produit cartésien des défaillances (capteur, bus, priorité, alarme, étage), avec élagage des combinaisons impossibles et preuve que la borne tient ou qu'une alarme technique se déclenche.
- **Fault injection** : capteur bloqué/mort/bruité/dérive, bus saturé, inversion de priorité, panne d'étage, alarmes concurrentes.
- **Jumeau de vérification** : cœur C11 pur + implémentation Python stdlib séparée, même contrat de sortie ; le désaccord est un bug réduit dichotomiquement.
- **Verdicts et rapports** : texte, JSON (une ligne par verdict), Markdown d'audit (empreinte SHA-256, horodatage, version).
- **Cible QNX** : resource manager `/dev/veille`, acquisition par pulses/timers, message passing avec priority inheritance, kernel trace comme preuve empirique.
- **Codelab** : « Prouver la latence d'une alarme médicale sur QNX » (bonus Best Codelab).

### 3.2 Hors périmètre (assumé)

Certification réelle IEC 60601/IEC 62304 (Veille produit des **artefacts** pour le dossier, pas la certification) ; matériel médical réel (capteurs simulés) ; algorithmes cliniques/diagnostic ; dossier patient/DSE ; UI graphique complète de moniteur ; remplacement du System Profiler (Veille le complète par la preuve).

---

## 4. Architecture

```
veille/
├── CONTRACT.md              # contrat gelé : chaîne, états, verdicts, formats octet pour octet
├── VEILLE-cahier-des-charges.md   # ce document
├── README.md                # pitch, garanties mesurées, état
├── Makefile                 # build + test (C + Python + différentiel) sans dépendance
├── LICENSE                  # MIT
├── core/                    # C11 PUR : ni horloge, ni fichier, ni socket, ni état global mutable
│   ├── include/veille/      #   chain.h state.h alarm.h proof.h verdict.h report.h
│   ├── src/                 #   chain.c state.c alarm.c proof.c verdict.c report.c
│   └── tests/               #   test_chain.c test_state.c test_alarm.c test_proof.c test_report.c
├── host/                    # Python 3 stdlib : jumeau indépendant + CLI + explorateur d'états
│   ├── veille/              #   __init__.py chain.py state.py alarm.py proof.py report.py cli.py
│   └── tests/               #   test_chain.py test_proof.py test_differential.py
├── target/                  # code QNX 8.0 : resource manager /dev/veille, capteurs simulés, alarme
│   ├── rm/                  #   resmgr_veille.c (resource manager)
│   ├── sensors/             #   sim_ecg.c sim_spo2.c sim_pa.c (générateurs d'échantillons)
│   ├── alarm/               #   alarm_sink.c (sortie alarme horodatée)
│   └── trace/               #   capture kernel trace → preuve empirique
├── scenarios/               # corpus de scénarios de défaillance (JSON) : nominaux, pires cas, fautifs
├── fixtures/                # configurations de chaîne (bornes, priorités) de référence
├── tests/                   # différentiel C↔Python, exploration exhaustive, fault injection, mutants
├── codelab/                 # chapitres : « prouver la latence d'une alarme médicale sur QNX »
├── docs/                    # SAFETY.md GAP.md DECISIONS.md VALIDATION.md IEC60601-8.md spec-fr.md spec-en.md
├── image/                   # build image QNX (mkifs) pour la démo QEMU
└── .github/workflows/       # CI : build C, tests Python, différentiel, exploration, garde <500 lignes
```

**Règle de portabilité.** `core/` ne lit aucun fichier et ne consulte aucune horloge : l'appelant fournit les échantillons, les timestamps et les tampons. Le même noyau est exécutable depuis Python, depuis un test unitaire, et sur cible QNX. La double implémentation (C dans `core/`, Python dans `host/`) n'est pas une duplication : c'est un **jumeau de vérification** indépendant, comme sur Ambre, Passerelle et Tamis.

**Règle de taille (AGENTS.md).** Tout fichier < 500 lignes, toute fonction < 50 lignes. Vérifié en CI (`wc -l`). Zéro duplication : helpers partagés entre `core/` et `target/`.

---

## 5. Contrat

### 5.1 Chaîne de traitement (figée)

```
sample(t0) → acquire(t1) → filter(t2) → decide(t3) → alarm(t4) → acknowledge(t5)
```

- Latence de bout en bout : `L = t4 - t0` (déclenchement de l'alarme).
- Latence d'acquittement : `A = t5 - t4`.
- Aucune étape ne remonte : un étage ne relit jamais l'échantillon brut. Toute erreur arrête la chaîne et produit un verdict `VEILLE_CHAIN_FAULT` avec l'étage fautif — **jamais** de reprise approximative sur un échantillon partiellement traité.
- Chaque étage porte un timestamp monotone (fourni par l'appelant ; `core/` ne lit pas d'horloge).

### 5.2 Bornes (configurables, défaut IEC 60601-1-8 à valider §10)

| Priorité | Latence alarme `B_alarm` | Latence acquittement `B_ack` | Profil sonore |
|---|---|---|---|
| haute | 100 ms | 60 s | 3 pulses rapides, pause |
| moyenne | 500 ms | 120 s | 2 pulses, pause longue |
| basse | 1000 ms | 300 s | 1 pulse, pause très longue |
| technique | 50 ms | — | continu (défaillance système) |

### 5.3 Verdicts (enum `veille_verdict_code`, sentinelle `VEILLE_VERDICT__COUNT`)

| # | Code | Sévérité | Porteur |
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

Un verdict porte toujours : `code`, `sev`, `message`. Les champs `chain_id`, `sensor_id`, `stage`, `state`, `bound_ms`, `latency_ms`, `config_sha256` sont **optionnels** (absents si non applicables).

### 5.4 API C (en-têtes sous `core/include/veille/`)

`verdict.h` :
```c
const char *veille_verdict_name(veille_verdict_code code);   /* hors plage -> "VEILLE_UNKNOWN" */
const char *veille_severity_name(veille_severity sev);        /* "info"|"warning"|"error" */
veille_severity veille_verdict_default_severity(veille_verdict_code code);
int veille_verdict_code_valid(veille_verdict_code code);      /* 1 si dans [0,COUNT) */
```

`proof.h` :
```c
/* Explore exhaustivement les états de défaillance de la chaîne et prouve la borne. */
int veille_proof_explore(const veille_chain_config *cfg,
                         const veille_fault_mask *mask,
                         veille_verdict *out, size_t cap, size_t *n_out);
/* Retourne : 0 si preuve complète (borne tenue partout), 1 si contre-exemple, <0 si erreur. */
```

`report.h` :
```c
long veille_report_text    (const veille_verdict *v, size_t n, char *buf, size_t cap);
long veille_report_json    (const veille_verdict *v, size_t n, char *buf, size_t cap);
long veille_report_markdown(const veille_verdict *v, size_t n,
                            const veille_report_meta *meta, char *buf, size_t cap);
int  veille_report_exit_code(const veille_verdict *v, size_t n);
```
Sémantique de retour : nombre d'octets qui auraient été écrits tampon plein (comme `snprintf`) ; `< 0` si argument invalide. Contenu toujours NUL-terminé si `cap > 0`.
`veille_report_meta` (fourni par l'appelant) : `config_file`, `config_sha256` (64 hex), `timestamp_utc` (ISO-8601), `veille_version`. Tout champ NULL est rendu `inconnu`.

### 5.5 Formats de sortie

**Texte** — une ligne par verdict, préfixe de sévérité aligné sur 5 caractères + 2 espaces :
```
ERROR  VEILLE_LATENCY_BOUND_EXCEEDED  chain=ecg_high  bound=100ms  latency=142ms  stage=decide  state=sensor_stuck|bus_saturated
WARN   VEILLE_TECHNICAL_ALARM  chain=spo2_med  stage=acquire  cause=sensor_dead
INFO   VEILLE_PROOF_COMPLETE  states=18432  bound=100ms  config_sha256=a3f9...
```
Termine par `OK` si aucun verdict error, sinon `FAILED <n> error(s)`.

**JSON** — une ligne par verdict, compact, ordre des clés **figé** : `code`, `sev`, `chain_id`, `sensor_id`, `stage`, `state`, `bound_ms`, `latency_ms`, `config_sha256`, `message`. Clés optionnelles omises quand absentes. Séparateurs `,` et `:` sans espace. Échappement identique C/Python (`"`→`\"`, `\`→`\\`, contrôles <0x20→`\u00XX` minuscule, UTF-8 ≥0x20 tel quel).

**Markdown d'audit** — pour dossier IEC 62304 :
```
# Rapport de preuve de latence — Veille

- Configuration : <config_file>
- Empreinte SHA-256 : <config_sha256|inconnu>
- Horodatage (UTC) : <timestamp_utc|inconnu>
- Version de Veille : <veille_version|inconnu>

## Synthèse
<OK / FAILED n error(s)>

## Propriétés vérifiées
### P1 — Latence d'alarme haute priorité ≤ 100 ms
- Méthode : exploration exhaustive de <N> états de défaillance
- Résultat : <borne tenue / contre-exemple>
- Contre-exemple le cas échéant : <état, latence, étage>
...
```

---

## 6. Exigences (S / C / X)

### 6.1 Socle (S) — démontrable sans QNX, sans licence

| ID | Exigence | Niveau |
|---|---|---|
| S1 | Chaîne `sample→acquire→filter→decide→alarm→ack` avec timestamps fournis par l'appelant, en C11 pur (`core/`) | S |
| S2 | Jumeau Python stdlib (`host/`) : même contrat de sortie, implémentation séparée | S |
| S3 | Test différentiel C↔Python sur corpus de scénarios : tout désaccord est un bug | S |
| S4 | Exploration exhaustive d'un sous-ensemble d'états (capteur × bus, 2 priorités) avec preuve de borne | S |
| S5 | Verdicts (10 codes) et rapports texte/JSON/Markdown avec empreinte SHA-256 | S |
| S6 | Fault injection : capteur bloqué/mort/bruité, bus saturé | S |
| S7 | `make test` vert sans QNX, sans QEMU, sans licence | S |
| S8 | CI GitHub Actions : build C (`-Wall -Wextra -Werror`), tests Python, différentiel, garde taille fichiers | S |

### 6.2 Complet (C) — ajoute la cible QNX

| ID | Exigence | Niveau |
|---|---|---|
| C1 | Resource manager `/dev/veille` exposant la chaîne d'alarme (API typée par message passing) | C |
| C2 | Acquisition périodique par pulses/timers noyau (pas de `sleep()`) | C |
| C3 | Priority inheritance `MsgSend` sur la voie critique : démontrée par kernel trace | C |
| C4 | Exploration exhaustive complète (tous les états : capteur × bus × priorité × alarme × étage) — **✅ fait : 4800 états, < 10 ms** | C |
| C5 | Kernel trace (`tracelogger`) capturé et converti en preuve empirique de latence | C |
| C6 | Fault injection sur cible : panne d'étage, `CHANNEL` disconnect notifié aux pairs | C |
| C7 | Image QNX (`mkifs`) bootable sur QEMU pour la démo | C |
| C8 | Codelab 4 chapitres : « prouver la latence d'une alarme médicale sur QNX » | C |
| C9 | Adaptive partitioning : partition critique (alarme) vs best-effort (UI), démontrée sous charge | C |

### 6.3 Extrême (X) — hors hackathon, documenté

| ID | Exigence | Niveau |
|---|---|---|
| X1 | Preuve formelle assistée (coq/why3) de la borne sur le modèle d'états | X |
| X2 | Intégration capteurs réels (ECG/SpO2 matériel) avec isolation galvanique | X |
| X3 | Dossier IEC 62304 complet (traçabilité exigences→tests→preuves) | X |
| X4 | Redondance failover de la chaîne d'alarme (deux calculateurs, comme Relais) | X |

---

## 7. Preuve par exploration exhaustive

### 7.1 Modèle d'états

La chaîne est modélisée comme un automate fini. Chaque étage a un ensemble d'états de défaillance :

| Dimension | États |
|---|---|
| Capteur | `ok`, `stuck` (valeur figée), `dead` (pas d'échantillon), `noisy` (aberrant), `drift` (dérive lente) |
| Bus | `ok`, `saturated` (charge), `spike` (pic de latence) |
| Priorité | `normal`, `inverted` (tâche basse priorité tient un verrou) |
| Alarme | `none`, `single`, `concurrent` (plusieurs), `locked`, `acked` |
| Étage | `ok`, `fault` (panne) pour chacun des 4 étages |

Produit cartésien complet (**mesuré, E5 validé**) : 5 × 3 × 2 × 5 × 32 = **4800 états**. L'estimation initiale « ~18432 » était erronée ; correction consignée dans `docs/VALIDATION.md`. Les 32 masques d'étage couvrent toutes les combinaisons de pannes des 5 étages (décision D10). Aucun élagage supplémentaire nécessaire : l'espace tient dans le budget d'un test unitaire (< 10 ms).

### 7.2 Propriété prouvée

**P1 (latence d'alarme).** Pour tout état atteignable `s` de la chaîne de priorité `p`, soit la latence `L(s) ≤ B_alarm(p)`, soit une alarme technique se déclenche avec `L_tech(s) ≤ B_tech`.

**P2 (non-manquement).** Pour tout état `s` où un seuil physiologique est franchi, une alarme de priorité correspondante est déclenchée (jamais de silence).

**P3 (acquittement).** Pour tout état `s` avec alarme active, l'acquittement est possible dans `B_ack(p)`.

### 7.3 Méthode

1. Énumérer tous les états atteignables (DFS sur l'automate, avec mémoïsation).
2. Pour chaque état, simuler la chaîne (cœur C ou jumeau Python) avec les timestamps pires-cas (latence maximale de chaque étage dans cet état).
3. Vérifier P1, P2, P3.
4. Si toutes tiennent → `VEILLE_PROOF_COMPLETE` avec nombre d'états et empreinte de config.
5. Si une tombe → `VEILLE_PROOF_COUNTEREXAMPLE` avec l'état fautif, la latence, l'étage (contre-exemple rejouable).

### 7.4 Preuve empirique (cible QNX)

Sur QEMU/RPi5 : kernel trace (`tracelogger`) capture les événements message-passing et scheduling de la chaîne réelle. Les timestamps de trace donnent la latence mesurée `L_measured`. La borne prouvée `B_proof` (exploration) doit couvrir `L_measured` : `L_measured ≤ B_proof`. L'écart est rapporté (marge). C'est la double preuve : **exhaustive** (modèle) + **empirique** (trace).

---

## 8. Tests et jumeau

| Test | But |
|---|---|
| Différentiel C↔Python | Même sortie sur même scénario ; tout désaccord = bug, réduit dichotomiquement |
| Exploration exhaustive | P1/P2/P3 sur tous les états ; contre-exemple rejouable |
| Fault injection | Capteur bloqué/mort/bruité, bus saturé, inversion de priorité, panne d'étage |
| Mutants | Injection de fautes dans `core/` pour vérifier que les tests les attrapent |
| Scénarios de référence | Corpus `scenarios/` : nominaux, pires cas, fautifs, résultats attendus gelés |
| Garde taille | CI : `wc -l` < 500 par fichier, fonctions < 50 lignes (grep) |
| Kernel trace (C) | Latence mesurée ≤ borne prouvée, sur QEMU |

---

## 9. Démo et vidéo (< 3 min)

1. **(0:00–0:30)** Le problème : une alarme médicale dont la latence n'est pas garantie = risque patient. IEC 60601-1-8 exige des délais.
2. **(0:30–1:15)** Veille sur QEMU : moniteur patient simulé (ECG/SpO2), chaîne capteur→alarme, alarme audible qui sonne dans la borne.
3. **(1:15–2:00)** Fault injection en direct : capteur bloqué → alarme technique dans 50 ms ; bus saturé → la priorité haute tient 100 ms ; inversion de priorité → détectée et corrigée (priority inheritance).
4. **(2:00–2:45)** La preuve : exploration exhaustive de 18432 états → `VEILLE_PROOF_COMPLETE` ; rapport Markdown d'audit avec empreinte SHA-256 pour dossier IEC 62304 ; kernel trace qui confirme la borne.
5. **(2:45–3:00)** Jumeau C↔Python : différentiel vert. Codelab.

Visuel : terminal + rapport Markdown + graphe d'états explorés + trace kernel (System Profiler). Pas de musique sous copyright, pas de marque tierce.

---

## 10. À valider avant d'écrire la moindre ligne de produit

| Essai | Question | Bloquant |
|---|---|---|
| E1 | Geler les bornes et priorités exactes d'IEC 60601-1-8 (délais de déclenchement, profils sonores, verrouillage) — la norme est payante ; utiliser les ordres de grandeur publiquement documentés et le signaler | oui (contrat §5.2) |
| E2 | Confirmer que la priority inheritance `MsgSend` est observable par kernel trace sur QEMU (événements visibles dans `tracelogger`) | oui (C3, preuve empirique) |
| E3 | Vérifier que `timer_create` + `MsgSendPulse` donnent une cadence périodique stable sous charge sur QEMU | oui (C2) |
| E4 | Confirmer que `CHANNEL` disconnect notifie bien les pairs à la mort d'un étage (microkernel) | oui (C6) |
| E5 | Mesurer le nombre réel d'états atteignables : **4800** (5×3×2×5×32), validé par `make test` et le différentiel C↔Python | ✅ fait |

---

## 11. Planning (12 nov → 15 déc, ~4 semaines)

| Semaine | Livrable |
|---|---|
| S1 (12–18 nov) | Contrat gelé, socle C (`core/`), jumeau Python (`host/`), différentiel vert, exploration sous-ensemble (S1–S7). E1–E2 validés. |
| S2 (19–25 nov) | Exploration exhaustive complète (C4), fault injection (S6/C6), rapports (S5), CI (S8). |
| S3 (26 nov–2 déc) | Cible QNX : resource manager `/dev/veille` (C1), pulses/timers (C2), priority inheritance + kernel trace (C3/C5), image QEMU (C7). |
| S4 (3–9 déc) | Adaptive partitioning (C9), codelab (C8), docs (SAFETY, GAP, VALIDATION), polissage. |
| Tampon (10–15 déc) | Vidéo <3 min, soumission Devpost, relecture, marge. |

---

## 12. Risques

| Risque | Impact | Mitigation |
|---|---|---|
| Bornes IEC 60601-1-8 inaccessibles (norme payante) | Contrat §5.2 approximatif | Utiliser ordres de grandeur publiés, documenter l'hypothèse, rendre les bornes configurables |
| Explosion combinatoire des états | Exploration trop lente | Élagage agressif (impossibles, symétries), mémoïsation, sous-ensemble S d'abord |
| Priority inheritance non observable sur QEMU | C3 non démontrable | E2 en amont ; sinon prouver par le modèle + trace partielle |
| Kernel trace trop volumineux | Preuve empirique lourde | Filtrer les événements de la chaîne uniquement, fenêtre temporelle bornée |
| Temps (4 semaines) | C/X non atteints | S d'abord (démontrable sans QNX), C ensuite, X documenté seulement |
| Chevauchement avec Ambre/Relais (même style preuve) | Jugé « pas substantiellement différent » | Veille = médical (IEC 60601-1-8), Ambre = automotive (UN R160), Relais = steer-by-wire (UN R79) : domaines, normes et chaînes distincts |

---

## 13. Statut des affirmations

| Affirmation | Statut |
|---|---|
| QNX n'a pas de framework d'alarme médicale IEC 60601-1-8 | À vérifier page à page dans SDP installé (M1) |
| Le System Profiler mesure mais ne prouve pas de borne pire-cas | Vérifié dans doc publique (M2) |
| Pas d'exploration exhaustive d'états dans QNX SDP | À vérifier (M3) |
| Priority inheritance `MsgSend` observable par kernel trace | À valider (E2) |
| Bornes IEC 60601-1-8 (100/500/1000 ms) | Ordres de grandeur publics, à geler (E1) |
| 4800 états atteignables (5×3×2×5×32) | ✅ mesuré (E5) — correction de l'estimation initiale « ~18432 », consignée dans VALIDATION.md |

Comme Tamis : trois affirmations ont été corrigées en cours de route sur Tamis ; Veille suivra la même discipline — toute correction est consignée ici.

---

## 14. Références

- IEC 60601-1-8 : Alarmes médicales — exigences générales (priorités, délais, profils sonores, verrouillage, acquittement, alarmes techniques).
- IEC 62304 : Logiciels de dispositifs médicaux — cycle de vie (traçabilité, vérification, validation).
- QNX SDP 8.0 : System Security Guide, Resource Manager Library, Kernel Trace (`tracelogger`), System Profiler, Adaptive Partitioning, Power-Safe File System.
- Projets frères : Ambre (EDR, preuve par exploration de power-cuts), Relais (failover latence bornée), Tamis (analyse statique de politiques), Passerelle (FS virtio/9P), Glane (capteurs/périphériques), Éclat (WAMR + capability broker).
- QNX Global Hackathon 2026 : https://qnx.devpost.com/ — règles, catégories, bonus.

---

## 15. Décisions de conception (à compléter dans docs/DECISIONS.md)

| # | Décision | Justification |
|---|---|---|
| D1 | Cœur C11 pur, pas d'horloge ni de fichier | Portabilité, testabilité sans QNX, jumeau Python comparable |
| D2 | Jumeau Python séparé, pas une copie | Vérification indépendante (désaccord = bug) |
| D3 | Exploration exhaustive sur modèle d'états, pas sur cible | Preuve pire-cas, rejouable, sans matériel |
| D4 | Kernel trace comme preuve empirique complémentaire | Double preuve : modèle + réel |
| D5 | Resource manager `/dev/veille` | API typée, isolation, un seul propriétaire de la chaîne |
| D6 | Bornes configurables (pas gravées) | IEC 60601-1-8 à geler (E1), normes évolutives |
| D7 | MIT | Cohérent avec les autres projets du portfolio |
| D8 | Codelab inclus | Bonus Best Codelab/Tutorial, pédagogie QNX |

---

*Fin du cahier des charges — Veille v0.1.*
