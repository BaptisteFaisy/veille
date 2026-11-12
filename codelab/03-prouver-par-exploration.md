# Chapitre 3 — Prouver par exploration exhaustive

Objectif : remplacer « j'ai mesuré 12 ms une fois » par « la latence **ne peut pas** dépasser la borne, dans **aucun** des 4800 états de défaillance atteignables — et voici le contre-exemple si elle le peut ».

---

## 3.1 Le modèle d'états

La chaîne est modélisée comme un automate fini. Chaque dimension a un ensemble fini d'états de défaillance :

| Dimension | États possibles | Nombre |
|---|---|---|
| **Capteur** | `ok`, `stuck` (valeur figée), `dead` (plus d'échantillon), `noisy` (aberrant), `drift` (dérive lente) | 5 |
| **Bus** | `ok`, `saturated` (saturé), `spike` (pic de latence) | 3 |
| **Priorité** | `normal`, `inverted` (tâche basse priorité tient un verrou) | 2 |
| **Alarme** | `none`, `single`, `concurrent`, `locked`, `acked` | 5 |
| **Étages** | masque de panne sur les 5 étages (acquire, filter, decide, alarm, ack) — toutes combinaisons | 2⁵ = 32 |

Espace complet : **5 × 3 × 2 × 5 × 32 = 4800 états**.

Pourquoi explorer les **32 combinaisons** d'étages et pas seulement « une panne à la fois » ? Parce qu'une panne peut en masquer une autre : si `decide` est en panne, le comportement de `filter` devient irrelevant. Explorer les pannes une par une ne prouve rien sur les combinaisons (décision D10).

4800 états, c'est trivial : l'exploration complète prend **moins de 10 ms** sur un poste de développement. Aucun élagage n'est nécessaire.

## 3.2 La propriété prouvée (P1)

> **P1 — Latence d'alarme bornée.** Pour tout état atteignable `s` de la chaîne de priorité `p` : soit la latence pire-cas `L(s) ≤ B_alarm(p)`, soit une alarme technique se déclenche avec `L_tech(s) ≤ B_tech`.

Et sa sœur (P2, vérifiée globalement — décision D9) :

> **P2 — Non-manquement.** Si la chaîne peut se rompre (panne d'un étage critique), alors la détection de panne `tech_detect_ms` tient dans la borne technique `bound_tech_ms`. Un capteur mort ne doit **jamais** produire du silence.

## 3.3 Lancer la preuve

### Sous-ensemble (pour commencer)

```
make proof
```

Sortie réelle :

```
=== exploration exhaustive (sous-ensemble S4) ===
INFO   VEILLE_PROOF_COMPLETE  bound=100ms  states=5
OK
```

Ici, seul le capteur varie (5 états) ; le reste est figé à `ok`. La latence pire-cas est 50 ms (base) + 10 ms (capteur bruité) = 60 ms ≤ 100 ms → **preuve complète**.

### Espace complet via la CLI

```
PYTHONPATH=host python3 -m veille.cli proof --bound 100
```

Sortie réelle :

```
ERROR  VEILLE_PROOF_COUNTEREXAMPLE  bound=100ms  latency=105ms  states=4800
FAILED 1 error(s)
```

**Un contre-exemple !** Avec une borne de 100 ms et les pénalités pire-cas (capteur figé +5 ms, pic de bus +50 ms), la latence atteint 105 ms. La preuve dit : « avec cette configuration, la borne de 100 ms **n'est pas** tenable ».

C'est exactement le genre de résultat qu'aucune mesure ponctuelle ne vous donnerait : le contre-exemple est **rejouable** et nomme l'état fautif.

### Corriger la configuration

```
PYTHONPATH=host python3 -m veille.cli proof --bound 200
```

```
INFO   VEILLE_PROOF_COMPLETE  bound=200ms  states=4800
OK
```

Avec une borne de 200 ms, le pire cas absolu (50 + 10 + 50 + 40 + 15 = **165 ms**) tient. La preuve est complète sur les 4800 états.

## 3.4 Les scénarios de référence

Les scénarios (`scenarios/*.json`) gèlent des configurations et leurs résultats attendus — comme des tests d'acceptation :

```
for s in scenarios/*.json; do echo "--- $s"; PYTHONPATH=host python3 -m veille.cli scenario "$s"; done
```

Sortie réelle :

```
--- scenarios/high_nominal.json
ERROR  VEILLE_PROOF_COUNTEREXAMPLE  bound=100ms  latency=105ms  states=4800
FAILED 1 error(s)
--- scenarios/high_safe.json
INFO   VEILLE_PROOF_COMPLETE  bound=200ms  states=4800
OK
--- scenarios/medium.json
INFO   VEILLE_PROOF_COMPLETE  bound=500ms  states=4800
OK
--- scenarios/tech_violation.json
ERROR  VEILLE_PROOF_COUNTEREXAMPLE  bound=50ms  latency=60ms  states=4800
FAILED 1 error(s)
```

Remarquez `tech_violation.json` : la borne d'alarme est large (P1 tenue), mais la **détection de panne** (60 ms) dépasse la borne technique (50 ms) → violation de **P2**. C'est le scénario « capteur mort qui reste silencieux trop longtemps » — exactement ce qu'IEC 60601-1-8 interdit.

## 3.5 Sorties machine : JSON et Markdown

Pour intégrer la preuve à une chaîne d'outils (CI, dossier d'audit) :

```
PYTHONPATH=host python3 -m veille.cli proof --bound 200 --json
```

```json
{"code":"VEILLE_PROOF_COMPLETE","sev":"info","bound_ms":200,"states_explored":4800,"message":"borne tenue sur tous les états"}
```

Une ligne par verdict, clés dans l'ordre figé du contrat, séparateurs compacts. Identique octet pour octet à la sortie C (c'est le différentiel qui le garantit).

## 3.6 Le rapport d'audit IEC 62304

```
PYTHONPATH=host python3 -m veille.cli proof --bound 200 --markdown
```

```markdown
# Rapport de preuve de latence — Veille

- Configuration : cli
- Empreinte SHA-256 : inconnu
- Horodatage (UTC) : inconnu
- Version de Veille : 0.1.0

## Synthèse
OK

## Propriétés vérifiées
### P1 — Latence d'alarme
- Méthode : exploration exhaustive de 4800 états
- Résultat : borne tenue
```

En production, l'appelant fournit la métadonnée (`veille_report_meta` en C, `meta` en Python) : nom du fichier de configuration, **empreinte SHA-256** de la configuration, horodatage UTC, version de Veille. Le certificat lie ainsi la preuve à une configuration **exacte** — si la configuration change, l'empreinte change, et la preuve doit être refaite. C'est ce qui rend le rapport exploitable dans un dossier IEC 62304 : l'auditeur peut vérifier que la preuve correspond bien à la configuration déployée.

## 3.7 Lire un contre-exemple

Un contre-exemple `VEILLE_PROOF_COUNTEREXAMPLE` porte :

- `states_explored` : nombre d'états parcourus avant de trouver la violation ;
- `bound_ms` : la borne qui n'est pas tenue ;
- `latency_ms` : la latence pire-cas de l'état fautif ;
- `state` (dans le rapport texte complet) : la combinaison de défaillances, ex. `sensor_stuck|bus_spike|prio_normal|alarm_none`.

C'est **rejouable** : vous pouvez reconstituer l'état fautif, l'injecter sur la cible (chapitre 4), et vérifier que la latence mesurée dépasse effectivement la borne. La preuve n'est pas une boîte noire.

## 3.8 Ce que la preuve ne dit pas

Honnêteté (comme `docs/SAFETY.md` §9) :

- **Le modèle n'est pas le réel.** Les pénalités (+5, +30, +50, +40, +15 ms) sont des **estimations pire-cas** à calibrer sur la cible réelle via le kernel trace (chapitre 4). Elles sont configurables.
- **La preuve porte sur le modèle d'états**, pas sur le matériel. La preuve empirique (trace) fait le pont.
- **Les bornes IEC 60601-1-8 sont des hypothèses** configurables, à geler après lecture de la norme (essai E1).

C'est précisément pour cela que la double preuve (modèle + cible) existe : aucune des deux ne suffit seule.

→ [Chapitre 4 : Porter sur QNX 8.0](04-porter-sur-qnx.md)
