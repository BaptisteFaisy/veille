# Chapitre 2 — Construire la chaîne

Objectif : une chaîne `acquisition → filtrage → décision → alarme` dont la latence est calculée de façon **déterministe**, vérifiable sur PC sans QNX, et dont deux implémentations indépendantes (C et Python) produisent exactement les mêmes octets.

---

## 2.1 Le contrat gelé d'abord

Avant d'écrire du code, on gèle le **contrat** (`CONTRACT.md`). C'est la source de vérité : formats octet pour octet, ordre des clés JSON figé, liste des verdicts. Pourquoi ? Parce que deux implémentations (C et Python) doivent être **comparables par différentiel**. Sans contrat précis, le différentiel ne prouve rien.

Le contrat définit la chaîne figée :

```
sample(t0) → acquire(t1) → filter(t2) → decide(t3) → alarm(t4) → acknowledge(t5)
```

Aucune étape ne remonte : un étage ne relit jamais l'échantillon brut. Toute erreur arrête la chaîne et produit un verdict — jamais de reprise approximative sur un échantillon partiellement compris.

## 2.2 Le cœur C11 **pur**

Règle d'or (décision D1) : `core/` ne lit **ni horloge, ni fichier, ni socket**, n'a **ni état global mutable**, et n'alloue rien que l'appelant ne fournisse.

Pourquoi une contrainte aussi stricte ? Parce que le même noyau doit s'exécuter dans trois contextes :

1. un test unitaire sur PC,
2. le jumeau Python (via le différentiel),
3. la cible QNX.

Si le cœur consultait l'horloge, le test de latence deviendrait non déterministe et le différentiel C↔Python caduc. **Le cœur calcule des latences fournies ; il ne les mesure pas.** La mesure est le rôle de `target/` (chapitre 4).

Concrètement, la latence pire-cas d'un état est une fonction pure :

```c
/* core/src/state.c */
long veille_state_worst_latency_ms(const veille_chain_config *cfg,
                                   const veille_fault_state *st) {
    if (!cfg || !st) return -1;
    if (veille_state_chain_broken(st)) return -1;   /* chaîne rompue → alarme technique */
    long sum = 0;
    for (int i = 0; i < VEILLE_STAGE__COUNT; i++) sum += cfg->stage_latency_ms[i];
    if (st->sensor == VEILLE_SENSOR_STUCK) sum += 5;
    if (st->sensor == VEILLE_SENSOR_NOISY) sum += 10;
    if (st->sensor == VEILLE_SENSOR_DRIFT) sum += 8;
    if (st->bus == VEILLE_BUS_SATURATED)   sum += 30;
    if (st->bus == VEILLE_BUS_SPIKE)       sum += 50;
    if (st->prio == VEILLE_PRIO_INVERTED)  sum += 40;
    if (st->alarm == VEILLE_ALARM_CONCURRENT) sum += 15;
    return sum;
}
```

Mêmes entrées → exactement mêmes sorties, octet pour octet. C'est ce qui rend la preuve **rejouable**.

## 2.3 Compiler et tester le socle

Depuis la racine du dépôt :

```
make test
```

Sortie réelle (extrait) :

```
cc -std=c11 -O2 -Wall -Wextra -Werror -Icore/include -MMD -MP -c core/src/proof.c -o core/src/proof.o
[core] built 6 objects
=== tests C ===
rc=1 n=1 states=4800 code=VEILLE_PROOF_COUNTEREXAMPLE latency=105
[OK] test_proof vert (4800 états, P1 + P2)
=== tests Python (jumeau) ===
......                                                                   [100%]
6 passed in 0.04s
=== différentiel C↔Python ===
C  : (4800, 105)
Py : (4800, 105)
[OK] différentiel C↔Python vert (states=4800, latency=105)
[OK] tous les tests verts
```

Trois choses à remarquer :

- **`-Werror`** : le socle compile sans aucun avertissement. Un avertissement est une erreur.
- **`-MMD -MP`** : le Makefile suit les dépendances d'en-têtes. Si vous modifiez `chain.h` (structure), tous les `.o` qui en dépendent sont recompilés. Sans cela, un décalage de structure silencieux produit des valeurs aberrantes sans lien avec la cause (c'est arrivé pendant le développement — décision D12).
- **4800 états, latence 105 ms** : ce sont les chiffres du chapitre 3.

## 2.4 Le jumeau Python : une deuxième implémentation, pas une copie

Décision D2 : `host/veille/` est une **implémentation séparée** du même contrat, pas un portage ligne à ligne du C.

Pourquoi ? Une copie dérive avec le C et ne prouve rien : les deux boguent ensemble. Deux implémentations **indépendantes** qui doivent produire le même octet détectent les bogues des deux côtés. C'est la méthode du « jumeau de vérification », utilisée sur Ambre, Passerelle et Tamis.

Le jumeau utilise la bibliothèque standard Python uniquement (aucune dépendance à installer). Exemple, l'exploration en Python :

```python
# host/veille/proof.py
STAGE_MASK_SPACE = 32   # 2**5, comme STAGE_MASK_SPACE en C

def explore(cfg, mask):
    bound = cfg.bound_alarm_ms
    result = {"states": 0, "broken": 0, "ce_state": None, "ce_latency": 0}
    def rec(st, dim):
        if dim == 5:
            result["states"] += 1
            lat = st.worst_latency_ms(cfg)
            if lat < 0:
                result["broken"] += 1
                return
            if lat > bound and result["ce_state"] is None:
                result["ce_state"] = st.copy()
                result["ce_latency"] = lat
            return
        # ... énumération des dimensions 0..4 selon le masque ...
    rec(FaultState(), 0)
    return result
```

## 2.5 Le différentiel C↔Python

Le test différentiel (`tests/differential.py`) exécute les deux implémentations sur le même scénario et compare les résultats :

```python
def run_py():
    cfg = ChainConfig(Priority.HIGH, 100, 60000, [5, 10, 10, 20, 5])
    mask = FaultMask(sensor=True, bus=True, prio=True, alarm=True, stage=True)
    rc, verdicts = proof_explore(cfg, mask)
    v = verdicts[0]
    return v.states_explored, v.latency_ms
```

Il compare avec la sortie du binaire C (`states=4800`, `latency=105`). Si les deux diffèrent, c'est un **bug** — réduit dichotomiquement jusqu'à trouver la divergence.

Le différentiel est lancé automatiquement par `make test`. Vous pouvez le lancer seul :

```
make differential
```

## 2.6 La démo hôte : mesurer pour de vrai

Le socle prouve une borne sur un **modèle**. La simulation hôte (`target/sim/sim.c`) mesure la latence **réelle** d'une chaîne qui tourne sur votre PC, avec horloge monotone (`clock_gettime`) et injection de pannes :

```
make demo
```

Sortie réelle (extrait) :

```
=== Veille — simulation hôte de la chaîne capteur→alarme ===

--- preuve modèle (exploration exhaustive) ---
INFO   VEILLE_PROOF_COMPLETE  bound=200  states=4800
OK

--- simulation (600 échantillons, pannes injectées) ---
[100] CAPTEUR FIGÉ  → alarme technique en 0.000 ms (borne 50 ms)
[300] CAPTEUR MORT  → alarme technique en 0.000 ms (borne 50 ms)
[309] bpm=124 (filtré) → ALARME haute en 0.000 ms (borne 200 ms)

--- bilan ---
alarmes physiologiques : 291 (latence max 0.001 ms, borne prouvée 200 ms)
alarmes techniques     : 8 (latence max 0.000 ms, borne 50 ms)
marge de sûreté        : 200 ms (borne prouvée - latence mesurée max)
[OK] L_measured <= B_proof sur tous les échantillons — double preuve cohérente.
```

C'est la **double preuve** du chapitre 1 en action : le modèle prouve `B_proof = 200 ms`, la simulation mesure `L_measured ≤ 0.001 ms`, donc `L_measured ≤ B_proof`. La marge de sûreté est énorme sur PC — sur cible QNX, elle sera plus réaliste (le kernel trace donnera les vraies latences de message passing, chapitre 4).

## 2.7 Ce que vous avez maintenant

- Un **contrat gelé** qui rend les deux implémentations comparables.
- Un **cœur C11 pur**, déterministe, testable sans QNX.
- Un **jumeau Python indépendant** qui vérifie le C par différentiel.
- Une **démo hôte** qui mesure la latence réelle et la confronte à la borne prouvée.

Tout cela tourne sur un poste ordinaire. Il manque la pièce maîtresse : la **preuve par exploration exhaustive** des 4800 états.

→ [Chapitre 3 : Prouver par exploration exhaustive](03-prouver-par-exploration.md)
