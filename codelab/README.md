# Codelab Veille — Prouver la latence d'une alarme médicale sur QNX 8.0

> *Ce codelab vous apprend à transformer une alarme médicale d'« elle a sonné en test » en « sa latence est **garantie** dans une borne, dans **chaque** état de défaillance atteignable, avec un certificat exploitable dans un dossier IEC 62304 » — en utilisant les mécanismes temps réel de QNX 8.0.*

Il accompagne le projet **Veille**, candidat au QNX Global Hackathon 2026 (catégorie Robotics & Medical). Il est écrit pour être **réellement exécuté** : toutes les commandes tournent sur un poste de développement ordinaire, **sans QNX, sans QEMU, sans licence**.

---

## Prérequis

- `gcc` (C11) et `make`
- `python3` (bibliothèque standard uniquement — aucune dépendance à installer)
- ~15 minutes

Vérifiez :

```
gcc --version && python3 --version && make --version
```

## Les chapitres

| # | Chapitre | Ce que vous apprenez | Durée |
|---|---|---|---|
| 1 | [Pourquoi une borne **prouvée**](01-pourquoi-une-borne-prouvee.md) | Alarme médicale = chemin critique à deadline ; IEC 60601-1-8 ; mesurer ≠ prouver ; pourquoi le déterminisme QNX est la bonne base | 5 min |
| 2 | [Construire la chaîne](02-construire-la-chaine.md) | Le contrat gelé ; `core/` C11 pur (ni horloge ni fichier) ; le jumeau Python indépendant ; compiler et tester ; le différentiel C↔Python | 10 min |
| 3 | [Prouver par exploration exhaustive](03-prouver-par-exploration.md) | Le modèle d'états (4800 états) ; lancer la preuve ; lire un contre-exemple ; les scénarios ; générer le rapport d'audit IEC 62304 | 10 min |
| 4 | [Porter sur QNX 8.0](04-porter-sur-qnx.md) | Resource manager `/dev/veille` ; cadence par pulses/timers ; priority inheritance `MsgSend` ; kernel trace comme preuve empirique ; adaptive partitioning | 8 min |

## Tout exécuter d'un coup

Depuis la racine du dépôt `veille/` :

```
make test     # socle C + jumeau Python + différentiel (doit être vert)
make proof    # exploration d'un sous-ensemble d'états
make demo     # simulation hôte : chaîne capteur→alarme + double preuve
```

Sortie attendue de `make test` (extrait) :

```
[OK] test_proof vert (4800 états, P1 + P2)
6 passed
[OK] différentiel C↔Python vert (states=4800, latency=105)
[OK] tous les tests verts
```

## Convention

- Les commandes sont à lancer depuis la racine du dépôt (`veille/`).
- `<...>` marque une valeur à remplacer ; tout le reste est littéral.
- Les sorties citées sont des sorties **réelles** obtenues sur un poste de développement.

## Licence

MIT, comme le projet. Aucune marque tierce n'est utilisée (règlement du hackathon).
