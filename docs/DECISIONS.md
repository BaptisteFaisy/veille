# Veille — Décisions de conception (DECISIONS)

> *Chaque décision est numérotée, motivée, et opposable. Le contrat gelé (`CONTRACT.md`) est la source de vérité des formats ; ce registre explique **pourquoi**.*

---

## D1 — Cœur C11 pur : ni horloge, ni fichier, ni socket

**Décision.** `core/` ne lit aucun fichier, ne consulte aucune horloge, n'alloue rien que l'appelant ne fournit pas. L'appelant fournit échantillons, timestamps et tampons.

**Pourquoi.** Le même noyau doit s'exécuter dans trois contextes : un test unitaire sur PC, le jumeau Python, et la cible QNX. Toute dépendance à l'environnement dans le cœur rend le test de.latence impossible et le différentiel C↔Python caduc.

**Conséquence.** Le cœur calcule des latences *données*, il ne les mesure pas. La mesure est le rôle de `target/` (horloge noyau, kernel trace).

---

## D2 — Jumeau Python séparé, pas une copie

**Décision.** `host/veille/` est une **deuxième implémentation** du contrat, écrite indépendamment, pas un portage ligne à ligne du C.

**Pourquoi.** Une copie dérive avec le C et ne prouve rien : les deux boguent ensemble. Deux implémentations séparées qui doivent produire **le même octet** detects les bogues des deux côtés. C'est la méthode « jumeau de vérification », utilisée sur Ambre, Passerelle et Tamis.

**Conséquence.** Le différentiel (`tests/differential.py`) est un test de premier plan, pas un bonus. Tout désaccord est un bug réduit dichotomiquement.

---

## D3 — Exploration exhaustive sur modèle d'états, pas sur cible

**Décision.** La preuve de P1/P2/P3 porte sur un **modèle** d'automate fini (5 dimensions, 4800 états), pas sur l'exécution réelle.

**Pourquoi.** Une preuve de borne pire-cas sur matériel réel exigerait d'injecter chaque combinaison de fautes sur une cible physique — impossible à répéter, impossible à certifier. Sur un modèle, l'énumération est **complète et rejouable**, et la cible fournit la preuve empirique complémentaire.

**Conséquence.** Deux niveaux de preuve : modèle (exhaustif, rejouable) + cible (empirique, kernel trace). Les deux doivent être cohérents : `L_measured ≤ B_proof`.

---

## D4 — Kernel trace comme preuve empirique complémentaire

**Décision.** `tracelogger` / `traceprinter` sur cible QNX fournit la latence réellement mesurée de la chaîne, confrontée à la borne prouvée.

**Pourquoi.** Le modèle prouve une borne ; seule la trace prouve que le système réel tient cette borne. Sans trace, le projet resterait une théorie élégante.

**Conséquence.** L'écart `B_proof − L_measured` est la **marge de sûreté**, reportée dans le certificat d'audit.

---

## D5 — Resource manager `/dev/veille`

**Décision.** Un seul processus possède la chaîne ; les clients (UI, journal, réseau) y accèdent par API typée (`read`/`write`/`devctl`), pas par fichier partagé.

**Pourquoi.** Un verrou partagé mal dimensionné est un bug de latence ; le resource manager QNX donne la propriété (un seul propriétaire, isolation d'adressespace) et la priority inheritance de `MsgSend` gratuitement.

**Conséquence.** Le client qui appelle l'alarme fait monter le sink à **sa** priorité pendant le message : la voie critique ne peut pas être préemptée.

---

## D6 — Bornes configurables, jamais gravées

**Décision.** `B_alarm` / `B_ack` / `B_tech` sont des champs de `veille_chain_config`, avec des défauts issus des ordres de grandeur publics d'IEC 60601-1-8.

**Pourquoi.** La norme est payante et évolutive ; les valeurs doivent pouvoir être re-gelées (essai E1) sans toucher au code. « Configurable par défaut » plutôt que « constant ».

**Conséquence.** Le certificat d'audit porte l'empreinte SHA-256 de la configuration : la preuve est liée aux bornes réellement utilisées.

---

## D7 — MIT

**Décision.** Licence MIT, cohérente avec le reste du portfolio (qnx-dossier, ambre, relais, passerelle, tamis).

---

## D8 — Codelab inclus dans le dépôt

**Décision.** `codelab/` fait partie du dépôt, pas d'un site externe.

**Pourquoi.** Le bonus **Best Codelab/Tutorial** exige une URL de codelab dans le formulaire de soumission ; un codelab versionné avec le code est plus crédible (le lecteur peut le refaire avec la version exacte testée) et survit à la fin du hackathon.

---

## D9 — P2 vérifiée globalement, pas par état

**Décision.** La propriété P2 (chaîne rompue → alarme technique bornée) est vérifiée **une fois** pour l'ensemble de l'espace : s'il existe un état à chaîne rompue, alors `tech_detect_ms ≤ bound_tech_ms`.

**Pourquoi.** La latence de détection d'une panne d'étage ne dépend pas du sous-etat de la panne : c'est une propriété de la supervision, pas de l'état. La vérifier par état produirait 4800 verdicts identiques.

**Conséquence.** Le verdict `VEILLE_PROOF_COUNTEREXAMPLE` porte le message `alarme technique hors borne (P2)` et les bornes techniques — distinct du contre-exemple de latence P1.

---

## D10 — Exploration complète sur les 32 masques d'étage

**Décision.** La dimension « étage » est explorée sur les **32 combinaisons** de pannes (les 5 étages, `2^5`), pas seulement sur « panne de decide ».

**Pourquoi.** Une panne d'étage peut en masquer une autre (p.ex. `decide` en panne masque le comportement de `filter`). Explorer les pannes une par une ne prouve rien sur les combinaisons. L'espace complet (4800 états) reste trivial à explorer et supprime cette weakness.

**Conséquence.** Espace complet = 5 (capteur) × 3 (bus) × 2 (priorité) × 5 (alarme) × 32 (étages) = **4800 états**, explorés en quelques millisecondes.

---

## D11 — Simulation hôte portable, cible QNX gardée séparée

**Décision.** `target/sim/sim.c` (portable, horloge POSIX) démontre la mesure de latence sur PC ; `target/rm/resmgr_veille.c` est gardé derrière `#ifdef __QNX__` et n'est pas compilé par le build hôte.

**Pourquoi.** Le socle doit rester démontrable **sans QNX, sans QEMU, sans licence** (exigence S7, comme Tamis). La cible QNX est un plus, pas un prérequis : on ne peut pas la tester en CI.

**Conséquence.** Le build hôte (`make test`, `make demo`) est vert partout ; la cible est vérifiée manuellement sur QEMU/RPi5 (essais E2–E4).

---

## D12 — Makefile avec suivi des dépendances d'en-têtes

**Décision.** `-MMD -MP` et `-include $(CORE_DEP)` dans le Makefile.

**Pourquoi.** Un changement de `chain.h` (structure modifiée) sans recompilation de `state.o` produit un **décalage de structure** silencieux : les tests échouent avec des valeurs aberrantes sans lien avec la cause. C'est arrivé pendant le développement (assertion `rc == 0` inexplicable) ; le correctif est structurel, pas un `make clean` à la main.

**Conséquence.** Toute modification d'en-tête recompile les objets dépendants. Le piège est documenté ici pour qu'il ne se reproduise pas.

---

*DECISIONS.md v0.1 — toute nouvelle décision s'ajoute ici avec sa motivation.*
