# Veille — Validation des essais (VALIDATION)

> *Les cinq essais du cahier des charges §10, avec leur statut. Aucun essai n'est « supposé réussi » : chacun est coché seulement quand la preuve existe (sortie de commande, trace, page de doc).*

---

## E1 — Geler les bornes et priorités IEC 60601-1-8

**Question.** Quelles sont les bornes exactes (délais de déclenchement, profils sonores, verrouillage, acquittement) imposées par IEC 60601-1-8 pour les priorités haute / moyenne / basse / technique ?

**Statut : 🚧 EN COURS — la norme est payante.**

Ce qui est fait :
- Les bornes utilisées (`B_alarm` 200 ms en démo, `B_tech` 50 ms, `B_ack` 60/120/300 s) sont des **ordres de grandeur** issus de la littérature publique sur les alarmes médicales, pas des valeurs extraites de la norme.
- Elles sont **configurables** (`veille_chain_config`, décision D6) : re-geler E1 ne touchera pas au code, seulement aux fixtures et aux scénarios.
- `docs/IEC60601-8.md` documente ce qui est connu publiquement et ce qui reste à vérifier page à page.

Ce qui reste :
- [ ] Obtenir la norme (achat, bibliothèque universitaire, ou via un fabricant de dispositifs médicaux).
- [ ] Extraire les valeurs exactes et les graver dans `fixtures/iec60601-8.json`.
- [ ] Mettre à jour `CONTRACT.md` §3 avec les valeurs gelées et la référence de page.

**Bloquant pour :** la soumission finale (les chiffres du certificat d'audit doivent être justifiés). **Non bloquant pour :** le socle technique, la démo, la méthode de preuve.

---

## E2 — Priority inheritance `MsgSend` observable par kernel trace

**Question.** Les événements `MsgSend`/`MsgReceive` et les changements de priorité (héritage) sont-ils visibles dans `tracelogger` sur QEMU, avec des horodatages suffisants pour calculer la latence de la voie critique ?

**Statut : ⏳ À VALIDER sur QEMU (nécessite QNX SDP 8.0 installé).**

Protocole prévu :
1. Installer QNX SDP 8.0 via QNX Everywhere (gratuit, non-commercial).
2. Démarrer QEMU x86_64 avec l'image `image/` (mkifs).
3. Lancer `resmgr_veille` + un sink d'alarme à priorité basse + une charge best-effort.
4. `tracelogger -o trace.kev` puis `traceprinter` : vérifier la présence des événements `MsgSend`, `MsgReceive`, `priority change` (héritage) sur la voie critique.
5. Calculer `L_measured` depuis la trace et comparer à `B_proof`.

**Critère de réussite :** les événements d'héritage de priorité sont visibles et horodatés ; `L_measured ≤ B_proof`.

**Bloquant pour :** C3, C5 (preuve empirique). **Non bloquant pour :** S1–S8 (socle hôte).

---

## E3 — Cadence périodique stable par `timer_create` + `MsgSendPulse`

**Question.** Un timer noyau à 10 ms donne-t-il une cadence stable sous charge sur QEMU (dérive < 1 ms) ?

**Statut : ⏳ À VALIDER sur QEMU.**

Protocole prévu : pulse de cadence à 10 ms, mesure de l'écart inter-pulses sur 10 000 pulses sous charge CPU best-effort, histogramme de la dérive.

**Critère de réussite :** dérive max < 1 ms sous charge.

---

## E4 — `CHANNEL` disconnect notifié à la mort d'un pair

**Question.** Quand le sink d'alarme meurt, le resource manager reçoit-il un pulse de disconnect, et dans quel délai ?

**Statut : ⏳ À VALIDER sur QEMU.**

Protocole prévu : tuer le sink (`kill -9`), mesurer le délai de notification du disconnect, vérifier que l'alarme technique (P2) part dans `B_tech`.

**Critère de réussite :** disconnect notifié, alarme technique dans `B_tech = 50 ms`.

---

## E5 — Nombre réel d'états atteignables après élagage

**Question.** Combien d'états l'exploration exhaustive parcourt-elle réellement ?

**Statut : ✅ VALIDÉ (mesuré).**

Résultat mesuré (commande `make test`, sortie du test C et du jumeau Python, différentiel vert) :

```
5 (capteur) × 3 (bus) × 2 (priorité) × 5 (alarme) × 32 (masques d'étage) = 4800 états
```

- Le chiffre « ~18432 » avancé dans le cahier des charges §7.1 était une **estimation erronée** (produit cartésien mal calculé). La valeur mesurée est **4800**.
- Correction consignée ici conformément à la discipline de Tamis (« toute correction est consignée »).
- Le cahier des charges et SAFETY.md sont mis à jour avec la valeur mesurée.
- Temps d'exploration : < 10 ms sur un poste de développement (4800 états, DFS, mémoïsation implicite).

**Conséquence :** l'espace complet tient dans le budget d'un test unitaire ; aucun élagage supplémentaire n'est nécessaire pour le niveau C. L'extension à d'autres dimensions (ex. 2 capteurs simultanés) multiplierait l'espace et nécessiterait un élagage — à documenter si ajoutée.

---

## Synthèse

| Essai | Statut | Bloquant pour |
|---|---|---|
| E1 bornes IEC 60601-1-8 | 🚧 en cours (norme payante) | soumission finale |
| E2 priority inheritance + trace | ⏳ à valider sur QEMU | C3, C5 |
| E3 cadence timer stable | ⏳ à valider sur QEMU | C2 |
| E4 CHANNEL disconnect | ⏳ à valider sur QEMU | C6 |
| E5 nombre d'états | ✅ validé : 4800 | — |

**Le socle S est vert sans QNX** (`make test`, `make demo`, différentiel C↔Python). Les essais E2–E4 nécessitent QNX SDP 8.0 (gratuit via QNX Everywhere) et seront menés sur QEMU avant la semaine 3 du planning.

---

*VALIDATION.md v0.1 — mettre à jour à chaque essai mené, avec la sortie réelle.*
