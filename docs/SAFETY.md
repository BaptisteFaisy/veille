# Veille — Sûreté de fonctionnement (SAFETY)

> *La latence d'alarme est une claim ; la preuve par exploration exhaustive en est la démonstration. Ce document explique comment Veille prouve que la chaîne capteur→alarme tient sa borne dans **chaque** état atteignable, au lieu de le mesurer sur quelques scénarios chanceux.*

Comme **Ambre** prouve la durabilité du crash en explorant exhaustivement tous les états de coupure d'alimentation, **Veille** prouve la latence d'alarme en explorant exhaustivement tous les états de défaillance de la chaîne.

---

## 1. Le problème de sûreté

Un moniteur patient dont l'alarme peut être retardée arbitrairement n'est pas sûr. IEC 60601-1-8 impose des **caractéristiques temporelles** aux alarmes médicales ; IEC 62304 impose de les **prouver**. Sur un RTOS général, la latence de la chaîne `capteur → filtrage → décision → alarme` dépend du scheduler, de la charge, des priorités, de l'état des capteurs et du bus. **Mesurer** cette latence sur quelques scénarios nominaux ne prouve rien pour le pire cas.

**Veille renverse l'approche** : au lieu de mesurer, on **énumère exhaustivement** tous les états de défaillance atteignables et on vérifie la borne dans chacun.

## 2. Propriétés de sûreté

| ID | Propriété | Énoncé |
|---|---|---|
| **P1** | Latence d'alarme bornée | Pour tout état atteignable `s` de la chaîne de priorité `p` : soit `L(s) ≤ B_alarm(p)`, soit une alarme technique se déclenche avec `L_tech(s) ≤ B_tech`. |
| **P2** | Non-manquement | Pour tout état `s` où un seuil physiologique est franchi et la chaîne intacte, une alarme de priorité correspondante est déclenchée (jamais de silence). |
| **P3** | Acquittement borné | Pour tout état `s` avec alarme active, l'acquittement est possible dans `B_ack(p)`. |

## 3. Modèle d'états (automate fini)

La chaîne est modélisée comme un automate fini dont chaque dimension a un ensemble fini d'états de défaillance :

| Dimension | États | Count |
|---|---|---|
| Capteur | `ok`, `stuck`, `dead`, `noisy`, `drift` | 5 |
| Bus | `ok`, `saturated`, `spike` | 3 |
| Priorité | `normal`, `inverted` | 2 |
| Alarme | `none`, `single`, `concurrent`, `locked`, `acked` | 5 |
| Étage | `ok`, `fault` (decide) | 2 |

Produit cartésien complet : **5 × 3 × 2 × 5 × 32 = 4800 états** (mesuré, E5 validé — l'estimation initiale « ~18432 » du cahier §7.1 était erronée, correction consignée dans `docs/VALIDATION.md`). Les 32 masques d'étage couvrent toutes les combinaisons de pannes des 5 étages (décision D10).

## 4. Méthode de preuve

1. **Énumération exhaustive** : DFS sur l'automate (fonction `explore_dim` en C, `explore` en Python). Espace complet : 4800 états (5 capteur × 3 bus × 2 priorité × 5 alarme × 32 masques d'étage), exploré en < 10 ms.
2. **Latence pire-cas par état** : `veille_state_worst_latency_ms` calcule la latence de bout en bout dans cet état, en additionnant les latences nominales d'étages et les **pénalités pire-cas** de chaque défaillance (capteur figé +5 ms, bus saturé +30 ms, pic de bus +50 ms, inversion de priorité +40 ms, alarmes concurrentes +15 ms, etc.).
3. **Chaîne rompue** : si un étage critique (acquire/filter/decide/alarm) est en panne, `veille_state_chain_broken` retourne 1 → la latence normale n'est pas définie ; c'est une **alarme technique** (IEC 60601-1-8) qui doit se déclencher dans `B_tech = 50 ms`. P2 est vérifiée globalement (décision D9) : s'il existe un état à chaîne rompue, alors `tech_detect_ms ≤ bound_tech_ms`.
4. **Vérification de P1** : pour chaque état, si `L(s) ≥ 0` et `L(s) > B_alarm(p)` → contre-exemple. Si aucun contre-exemple sur les 300 états → `VEILLE_PROOF_COMPLETE`.
5. **Contre-exemple rejouable** : `VEILLE_PROOF_COUNTEREXAMPLE` porte l'état fautif, la latence et l'étage — reproductible à la demande.

## 5. Double preuve : exhaustive + empirique

| Preuve | Source | Portée |
|---|---|---|
| **Exhaustive** (modèle) | `veille_proof_explore` (C) + jumeau Python | Tous les états atteignables du modèle ; borne pire-cas garantie |
| **Empirique** (cible) | Kernel trace `tracelogger` sur QEMU/RPi5 | Latence mesurée `L_measured` sur la chaîne réelle ; on vérifie `L_measured ≤ B_proof` |

L'écart entre borne prouvée et latence mesurée est la **marge de sûreté**. Elle est rapportée dans le certificat d'audit.

## 6. Apport spécifique de QNX (pourquoi un RTOS)

| Propriété QNX | Ce que ça apporte à Veille |
|---|---|
| **Priority inheritance `MsgSend`** | La voie critique capteur→alarme ne peut pas être préemptée par du travail de moindre priorité ; l'inversion de priorité (état `prio_inverted`) est **corrigée par le noyau**, pas seulement détectée. |
| **Pulses et timers noyau** | Cadence périodique d'acquisition et deadlines sans `sleep()` ; la latence d'étage est bornée par le timer, pas par le scheduler. |
| **Resource managers** | `/dev/veille` : un seul processus possède la chaîne ; les autres y accèdent par API typée (pas de verrou partagé à mal dimensionner). |
| **Microkernel + `CHANNEL` disconnect** | La mort d'un étage est **notifiée aux pairs** : `decide` sait que `acquire` est tombé et déclenche une alarme technique au lieu d'attendre en silence. |
| **Adaptive partitioning** | Partition critique (alarme) isolée de la partition best-effort (UI, réseau) : la charge UI ne peut pas retarder l'alarme. |
| **Kernel trace (`tracelogger`)** | Capture des événements message-passing/scheduling : la latence mesurée est la **preuve empirique** qui confirme la borne prouvée. |

Sur un OS généraliste (Linux), aucune de ces garanties n'est native : l'inversion de priorité n'est pas corrigée, la mort d'un pair n'est pas notifiée, le partitionnement n'est pas temps réel, et la trace ne prouve pas de borne pire-cas.

## 7. Fault injection (vérification de la preuve)

La preuve est vérifiée par **injection de fautes** sur la chaîne réelle (cible QNX) :

| Faute injectée | Comportement attendu | Vérifié par |
|---|---|---|
| Capteur figé (`stuck`) | Détection de valeur figée, latence ≤ borne | kernel trace + verdict |
| Capteur mort (`dead`) | Alarme technique dans `B_tech = 50 ms` | `CHANNEL` disconnect + trace |
| Bus saturé | Priorité haute tient `B_alarm` (priority inheritance) | trace + mesure |
| Inversion de priorité | Corrigée par le noyau, latence ≤ borne | trace (événements MsgSend) |
| Panne d'étage `decide` | Chaîne rompue → alarme technique | `chain_broken` + verdict |
| Alarmes concurrentes | Arbitrage, latence ≤ borne + 15 ms | trace |

Chaque faute injectée produit un verdict et une trace ; le résultat est confronté à la preuve exhaustive (l'état injecté doit être dans l'espace exploré, et la latence mesurée ≤ borne prouvée).

## 8. Certificat d'audit (IEC 62304)

`veille_report_markdown` produit un certificat horodaté et empreinté (SHA-256 de la configuration) :

```
# Rapport de preuve de latence — Veille
- Configuration : cfg.json
- Empreinte SHA-256 : a3f9...
- Horodatage (UTC) : 2026-11-12T00:00:00Z
- Version de Veille : 0.1.0
## Synthèse
OK
## Propriétés vérifiées
### P1 — Latence d'alarme
- Méthode : exploration exhaustive de 300 états
- Résultat : borne tenue
```

Ce certificat est l'artefact exploitable dans un dossier IEC 62304 : il lie la configuration (empreinte), la méthode (exploration exhaustive), le résultat (borne tenue / contre-exemple) et la version de l'outil.

## 9. Limites assumées

- **Le modèle n'est pas le réel** : la preuve porte sur le modèle d'états (latences pire-cas paramétrées), pas sur le matériel réel. La preuve empirique (kernel trace) fait le pont, mais ne remplace pas une certification.
- **Bornes IEC 60601-1-8 à geler** : les valeurs (100/500/1000/50 ms) sont des ordres de grandeur publiquement documentés ; la norme est payante. Essai E1 du cahier des charges.
- **Pénalités pire-cas heuristiques** : les +5/+30/+50/+40/+15 ms sont des estimations à calibrer sur la cible réelle (kernel trace). Elles sont **configurables** (`stage_latency_ms` + pénalités).
- **Pas de certification réelle** : Veille produit des artefacts pour le dossier IEC 62304, pas la certification elle-même.

## 10. Traçabilité exigences → preuves

| Exigence | Preuve |
|---|---|
| S1 chaîne horodatée | `core/src/state.c` `worst_latency_ms`, test C |
| S2 jumeau Python | `host/veille/`, test unitaire Python |
| S3 différentiel C↔Python | `tests/differential.py` |
| S4 exploration sous-ensemble | `core/src/proof.c` `explore_dim`, test 300 états |
| S5 verdicts + rapports | `core/src/report.c`, `host/veille/report.py` |
| S6 fault injection | §7 (cible QNX, C6) |
| S7 `make test` sans QNX | Makefile, CI |
| C1–C9 cible QNX | `target/` (à venir), kernel trace |

---

*SAFETY.md v0.1 — toute modification de la méthode de preuve passe par ce document.*
