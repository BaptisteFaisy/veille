# Veille — dossier de soumission (QNX Global Hackathon 2026)

Candidat **QNX Global Hackathon 2026**, catégorie **Robotics & Medical**.
Dépôt des soumissions : **15 décembre 2026, 14 h ET**.
Cible les bonus **Best use of QNX-specific Technologies** (message passing,
priority inheritance, resource managers, pulses/timers) et **Best Codelab**.

---

## Titre

> **Veille — un moniteur patient QNX 8.0 dont la latence d'alarme est bornée
> et prouvée, pas seulement mesurée.**

## Pitch (30 secondes, 3 phrases)

1. Veille traite la chaîne *capteur → alarme* comme un chemin critique à deadline,
   et **prouve** que la borne tient dans **chacun des 4800 états de défaillance**
   atteignables (capteur figé ou mort, bus saturé, inversion de priorité, alarmes
   concurrentes) — au lieu de la mesurer sur quelques scénarios chanceux.
2. La chaîne **tourne sur un QNX 8.0 réel** (émulateur QEMU) : 291 alarmes
   physiologiques et 8 techniques, toutes dans la borne, avec un **jumeau Python**
   de vérification et un **resource manager `/dev/veille`** qui valide les quatre
   issues de la chaîne.
3. Et **2401 battements de vrais patients** (MIT-BIH) sont rejoués dans la chaîne,
   sur la cible — accompagnés d'un document d'honnêteté qui dit exactement ce qui
   reste à démontrer.

## Résumé (≈ 200 mots)

Une alarme médicale est soumise à des délais (IEC 60601-1-8) et l'obligation de
les **prouver** (IEC 62304). QNX fournit le déterminisme — priority inheritance,
pulses, resource managers, kernel trace — mais **n'outille pas la preuve** : le
System Profiler mesure des échantillons, il n'explore pas les états de défaillance.

Veille occupe cet espace. Il modélise la chaîne capteur → alarme comme un chemin
critique et **prouve** la borne `B_alarm` (100/500/1000 ms, 50 ms pour l'alarme
technique) par **exploration exhaustive de 4800 états**, avec une **double
implémentation** (socle C11 pur + jumeau Python) mutuellement contrôlées : le
désaccord est un bug, réduit dichotomiquement.

La démonstration est **réelle** : la chaîne compile avec le vrai `qcc` du SDP 8.0,
s'exécute sur QNX 8.0 (QEMU/KVM) et rend le même bilan que sur l'hôte — 291
alarmes physiologiques, 8 techniques, `L_measured ≤ B_proof`. Le resource manager
`/dev/veille` valide les quatre issues (normal, tachycardie, capteur figé, capteur
mort), et des **ECG de vrais patients** (PhysioNet, SHA-256 vérifié) sont rejoués :
2401 battements réels écrits dans `/dev/veille`. Le passage sur cible a trouvé
**5 défauts réels**, corrigés.

Le projet assume ses limites : E2, E3 et E4 sont **déclarés non démontrés**, avec
la cause exacte de chacun ([`docs/LIMITS.md`](LIMITS.md)).

## Ce qui est nouveau (les trous documentés)

- **IEC 60601-1-8** impose des caractéristiques temporelles d'alarme ; **IEC 62304**
  impose de les prouver (traçabilité, vérification).
- **QNX 8.0** donne le déterminisme mais **n'outille pas la preuve de latence** :
  le System Profiler échantillonne, il ne certifie pas une borne pire-cas.
- **Veille comble l'écart** : preuve par **exploration exhaustive** (pas par mesure),
  **double implémentation** (C↔Python), et **exécution sur cible QNX réelle**.
  Contexte documenté : [`README.md`](../README.md) §« Pourquoi ».

## Architecture (en 5 lignes)

- `core/` — socle **C11 pur** (ni horloge, ni fichier, ni socket) : verdict, chaîne, état, alarme, preuve, rapport.
- `host/` — **jumeau Python** stdlib : même contrat, implémentation indépendante + CLI (`--proof`, `--scenario`).
- `target/` — **QNX 8.0** : resource manager `/dev/veille` (`rm`), simulation capteur (`sim`), couche temps (`port`).
- `preuve/qnx80/` — **journaux bruts** des exécutions sur cible (commande, `uname`, sortie, code de sortie).
- `docs/` + `site/` — cahier des charges, contrat gelé, preuve, codelab, **site statique** publié par GitHub Pages.

## Les chiffres

| Chiffre | Valeur | Source |
|---|---|---|
| États de défaillance explorés | **4800** (5×3×2×5×32) | [`docs/VALIDATION.md`](VALIDATION.md) §E5, `tests/differential.py` |
| Alarmes démo sur cible | **291 physiologiques + 8 techniques**, `L_measured ≤ B_proof` | [`docs/QNX-EVIDENCE.md`](QNX-EVIDENCE.md) §3.1 |
| Exploration sur cible | **0,13 s** (`real 0m0.126s`) | [`docs/QNX-EVIDENCE.md`](QNX-EVIDENCE.md) §3.2 |
| Battements réels écrits dans `/dev/veille` | **2401** (MIT-BIH 222, 2500 pics R) | [`docs/QNX-EVIDENCE.md`](QNX-EVIDENCE.md) §3.4 |
| Défauts trouvés en passant sur cible | **5**, tous corrigés | [`docs/QNX-EVIDENCE.md`](QNX-EVIDENCE.md) §4 |

> Le temps d'exécution de l'exploration dépend de la charge de l'invité
> (0,13 s au repos, ≈ 2,8 s sous charge) : **le verdict ne change pas**, seul le
> temps mural varie — voir [`docs/LIMITS.md`](LIMITS.md) §2.

## Ce qui est démontré / non démontré

**Démontré** : compilation `make qnx` (vrai qcc), exécution sur QNX 8.0 réel (QEMU),
démo C identique hôte/cible, exploration 4800 états sur cible, resource manager
(4 issues), rejeu d'ECG réels (2401 battements écrits dans `/dev/veille`).

**Non démontré** (assumé, documenté dans [`docs/LIMITS.md`](LIMITS.md)) :
- **E2** — priority inheritance observable par trace noyau (traceprinter du SDP
  installé refuse les traces de l'image récente) ;
- **E3** — dérive de cadence du timer non chiffrée ;
- **E4** — notification de disconnect par canal client ;
- pas de **matériel réel**, pas de **validation clinique**, bornes IEC 60601-1-8 =
  **ordres de grandeur** (norme payante non lue), jeux de données de **patients différents**.

## Liens

- **Dépôt** : <https://github.com/BaptisteFaisy/veille> (dépôt renommé `Tradoooo/veille` ; l'ancienne adresse redirige)
- **Site** : <https://baptistefaisy.github.io/veille/>
- **Vidéo** (2 min 40 s) : `preuve/video/veille.mp4` — régénérée par
  `bash preuve/video/montage.sh` (storyboard : [`docs/VIDEO.md`](VIDEO.md)).
  À héberger sur le Devpost (le fichier MP4 n'est pas commité, voir `.gitignore`).

---

## Six questions probables du jury — réponses préparées

### 1. « Comment votre preuve peut-elle se tromper ? »

De trois façons, et on s'en protège explicitement. (a) Un bug dans une
implémentation : le socle C11 et le jumeau Python sont **deux implémentations
séparées** du même contrat, leur désaccord est un bug réduit dichotomiquement
(`tests/differential.py`). (b) Ne tester que des cas heureux : on **explore les
4800 états exhaustivement**, et la preuve produit un **contre-exemple** quand la
borne est violée — c'est le cas attendu `bound=100ms latency=105ms`
([`docs/QNX-EVIDENCE.md`](QNX-EVIDENCE.md) §3.2). (c) Prétendre vérifier ce qu'on
n'a pas vérifié : la liste exacte des non-démontrés est dans
[`docs/LIMITS.md`](LIMITS.md) §2.

### 2. « Qu'est-ce qui n'est pas réel dans votre démo ? »

Trois choses, dites à l'écran et dans les docs. La cible est un **émulateur
(QEMU/KVM), pas du matériel** ; le signal entré dans `/dev/veille` est du **bpm
déduit de l'ECG réel**, pas l'acquisition brute ; et les **bornes** sont des ordres
de grandeur, pas des valeurs lues dans la norme payante.
— [`docs/LIMITS.md`](LIMITS.md) §4–5–3, [`docs/QNX-EVIDENCE.md`](QNX-EVIDENCE.md) §6.

### 3. « Pourquoi QNX ? »

Parce que QNX fournit exactement le déterminisme nécessaire (priority inheritance
`MsgSend`, pulses/timers, resource managers, kernel trace) et qu'il est présent dans
l'embarqué médical — mais **n'outille pas la preuve de latence d'alarme** : c'est
précisément le trou que Veille comble. Et on le prouve sur QNX, pas sur Linux :
`make qnx` avec le vrai `qcc`, exécution sur QNX 8.0 réel, resource manager
`/dev/veille`. — [`README.md`](../README.md) §« Pourquoi » et §« Sur cible QNX 8.0 »,
[`docs/QNX-EVIDENCE.md`](QNX-EVIDENCE.md).

### 4. « Et si le capteur ment ? »

C'est modélisé : les états `sensor_stuck` (figé), `sensor_dead` (mort) et `sensor_noisy`
(bruité) font partie des 4800 états explorés, et le resource manager rend
`VEILLE_TECHNICAL_ALARM … sensor_stuck` / `sensor_dead` dans `B_tech = 50 ms` — les
deux verdicts sont réellement produits sur cible (`preuve/qnx80/preuve-resmgr-cible-*.log`,
[`docs/QNX-EVIDENCE.md`](QNX-EVIDENCE.md) §3.3). Honnêteté : la détection « figé » est
**heuristique** (déclenche sur deux bpm consécutifs égaux) et sa correction est en cours
(voir [`docs/LIMITS.md`](LIMITS.md) §7).

### 5. « Votre latence mesurée est-elle un vrai chiffre ? »

Oui, mais il faut distinguer. La **preuve** est la borne : `L_measured = 0,001 ms ≪
B_proof = 200 ms`, relevée **sur la cible** sur tous les échantillons — c'est un vrai
chiffre mesuré, mais **dans un émulateur**, donc il ne vaut pas pour du matériel.
La **garantie** vient de l'exploration exhaustive (4800 états), pas de la mesure.
— [`docs/QNX-EVIDENCE.md`](QNX-EVIDENCE.md) §3.1, [`docs/LIMITS.md`](LIMITS.md) §4.

### 6. « Que reste-t-il à faire ? »

Quatre choses, classées par valeur de preuve : **E2** (relire la trace déjà capturée
avec un SDP de même version), **E3** (mesurer la dérive du tick sous charge), **E4**
(disconnect par canal client), puis **matériel réel** et **clinique** ; enfin **E1**
(lire la norme et geler les bornes exactes). Les protocoles de E2/E3/E4 sont déjà
rédigés dans [`docs/VALIDATION.md`](VALIDATION.md), le plan complet dans
[`docs/LIMITS.md`](LIMITS.md) §8.