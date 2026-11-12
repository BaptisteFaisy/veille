# Veille — limites de la preuve (document d'honnêteté)

Ce document récapitule **exactement** ce que la preuve Veille établit et ce
qu'elle n'établit pas. Il est un argument (la preuve est solide précisément
parce que ses bornes sont dites), pas une liste de faiblesses. Chaque assertion
renvoie à un fichier du dépôt.

Les journaux bruts cités sont dans `preuve/qnx80/` (un fichier par exécution).
Le compte rendu factuel est [`docs/QNX-EVIDENCE.md`](QNX-EVIDENCE.md).

---

## 1. Ce que la preuve établit

1. **La chaîne compile et s'exécute sur QNX 8.0 réel.** `make qnx` avec le vrai
   `qcc` du SDP 8.0 (cible `gcc_ntox86_64`) produit `veille-sim` et `veille-rm`
   (ELF x86_64). La démo C donne **le même bilan sur la cible que sur l'hôte** :
   291 alarmes physiologiques, 8 techniques, `L_measured ≤ B_proof`.
   — [`docs/QNX-EVIDENCE.md`](QNX-EVIDENCE.md) §2–3, `docs/QNX-BUILD.md`.
2. **L'exploration exhaustive des 4800 états de défaillance s'exécute sur la
   cible** et retrouve le contre-exemple attendu (`bound=100ms latency=105ms`).
   Le jumeau Python (stdlib seule) et le socle C11 sont en accord sur le résultat.
   — [`docs/QNX-EVIDENCE.md`](QNX-EVIDENCE.md) §3.2, `tests/differential.py`.
3. **Le resource manager `/dev/veille` est un vrai nœud QNX** : les quatre issues
   de la chaîne (normal, tachycardie, capteur figé, capteur mort) rendent les
   quatre verdicts du contrat.
   — [`docs/QNX-EVIDENCE.md`](QNX-EVIDENCE.md) §3.3.
4. **Des ECG de patients réels sont rejoués dans la chaîne sur la cible** :
   2500 pics R détectés sur MIT-BIH 222, **2401 battements réels écrits dans
   `/dev/veille`** (bpm 43 → 181,5). Les fichiers sources sont vérifiés par
   empreinte SHA-256 contre PhysioNet.
   — [`docs/REAL-DATA.md`](REAL-DATA.md), [`docs/QNX-EVIDENCE.md`](QNX-EVIDENCE.md) §3.4.
5. **Le passage sur cible a trouvé 5 défauts réels**, tous corrigés (`io_write`
   et le code de retour, lecture via `resmgr_msgget`, une valeur par écriture,
   `O_CREAT` sur périphérique, disconnect parasite).
   — [`docs/QNX-EVIDENCE.md`](QNX-EVIDENCE.md) §4.

## 2. Ce que la preuve n'établit PAS

Ces trois essais du cahier des charges sont **explicitement non validés** — aucun
fichier du dépôt ne prétend le contraire :

| Essai | Question | Statut | Cause précise |
|---|---|---|---|
| **E2** | L'héritage de priorité `MsgSend` est-il observable par trace noyau ? | **non démontré** | Le `traceprinter` du SDP installé (v1.02, janvier 2025) refuse les traces de l'image de septembre 2026 — `TRACEPARSER: function call traceparser() failed, internal error code(12)`. Il faut un SDP de même version que l'image. — [`docs/QNX-EVIDENCE.md`](QNX-EVIDENCE.md) §5 |
| **E3** | La cadence `timer_create` + `MsgSendPulse` est-elle stable sous charge ? | **non mesuré** | La dérive du tick (10 ms) n'a pas été chiffrée sur cible. — [`docs/VALIDATION.md`](VALIDATION.md) §E3 |
| **E4** | La mort d'un client est-elle notifiée par `CHANNEL` disconnect ? | **non démontré** | La notification `_PULSE_CODE_DISCONNECT` ne remonte pas au niveau du dispatch pour un client iofunc ; l'alarme technique sur déconnexion reste à implémenter. — [`docs/QNX-EVIDENCE.md`](QNX-EVIDENCE.md) §5 |
| **E1** | Les bornes et priorités IEC 60601-1-8 sont-elles **gelées** ? | **partiel** | Voir §3 ci-dessous. |

À cela s'ajoutent : **pas de matériel réel** (voir §4), **pas de validation
clinique** (voir §5), et des **jeux de données de patients différents** (voir §6).

> **Temps de calcul, pas résultat.** Le temps d'exécution de l'exploration dépend
> de la charge de l'invité : **0,13 s** sur un invité au repos (mesure de
> référence, [`docs/QNX-EVIDENCE.md`](QNX-EVIDENCE.md) §3.2), **≈ 2,8 s** sur
> l'invité chargé lors de la prise des captures vidéo
> (`preuve/video/captures/03-exploration-4800-etats.txt`). Le **verdict est
> identique** dans les deux cas (même contre-exemple, mêmes 4800 états) : c'est le
> temps mural qui varie, pas la conclusion.

## 3. Hypothèses du modèle — les bornes IEC 60601-1-8

- Les bornes utilisées (`B_alarm` 100/500/1000 ms par priorité, `B_tech` 50 ms,
  `B_ack` 60/120/300 s) sont des **ordres de grandeur issus de la littérature
  publique** sur les moniteurs de signes vitaux, **pas** des valeurs lues dans la
  norme. La norme **IEC 60601-1-8 est payante et n'a pas été lue**.
  — [`docs/IEC60601-8.md`](IEC60601-8.md) (avertissement d'honnêteté en tête),
  [`CONTRACT.md`](CONTRACT.md) §3, [`docs/VALIDATION.md`](VALIDATION.md) §E1.
- Les bornes sont **configurables** (`veille_chain_config`) : geler E1 (obtenir la
  norme et extraire les valeurs exactes) ne touchera pas au code, seulement aux
  fixtures. Le certificat d'audit horodaté et empreinté reste un **artefact
  méthode** (exploration exhaustive), pas une attestation de conformité normative.

## 4. Limites de l'émulateur — pas du matériel

- La cible est un **x86_64 virtualisé** (QEMU + KVM, image QNX Everywhere Quick
  Start). Aucune mesure ne vaut pour un vrai moniteur patient ni pour une cible
  **embarquée** (ARM/SoC médical, horloges et bus réels).
  — [`docs/QNX-EVIDENCE.md`](QNX-EVIDENCE.md) §1 et §6.

## 5. Statut non clinique

- Le signal **saisi** par `/dev/veille` est du **bpm déduit de l'ECG réel par le
  client** ; le rejeu du signal brut (acquisition → filtrage) n'est fait que par
  le **jumeau Python**.
- La **détection de pics R est heuristique** (seuil adaptatif, non clinique) :
  sur un ECG réel en fibrillation atriale, le bpm oscille fortement.
  — [`docs/QNX-EVIDENCE.md`](QNX-EVIDENCE.md) §6, [`docs/REAL-DATA.md`](REAL-DATA.md) « limites ».
- **Veille est un framework logiciel**, pas un dispositif médical certifié ; il
  produit des artefacts pour un dossier IEC 62304, pas une homologation.

## 6. Jeux de données de patients différents

- **MIT-BIH** : ECG seul (2 dérivations). **BIDMC** : ECG **et** SpO2/HR **du
  même patient et du même séjour** (le seul couple synchronisé disponible).
  **Sleep-EDF** : ECG et pression artérielle, **mais pas de SpO2**.
- On ne peut donc **pas** affirmer « ECG + SpO2 + pression artérielle du même
  patient » : ce triplet n'existe pas dans les données téléchargées.
- Les fichiers BIDMC ne sont **pas les octets d'origine** du moniteur : le
  sous-ensemble *matched* a été reprocessé par PhysioNet.
  — [`docs/REAL-DATA.md`](REAL-DATA.md) §1.1–1.2.

## 7. Défaut connu de la détection « capteur figé »

- La chaîne déclenche l'alarme « capteur figé » dès que **deux valeurs de bpm
  consécutives arrondies sont égales**. Sur un ECG réel, c'est un vrai
  enseignement : le diagnostic doit porter sur le **signal brut** et non sur le
  bpm arrondi. **Ce défaut est en cours de correction**, au niveau du signal.
  — [`docs/QNX-EVIDENCE.md`](QNX-EVIDENCE.md) §6,
  [`docs/REAL-DATA.md`](REAL-DATA.md) « limites ».

## 8. Ce qui rendrait la preuve plus forte

1. **E2** : installer un SDP 8.0 de la même version que l'image (septembre 2026)
   et relire la trace capturée (le fichier, 3,4 Mo, est déjà enregistré).
2. **E3** : mesurer la dérive du tick sur 10 000 pulses sous charge (protocole
   déjà rédigé dans [`docs/VALIDATION.md`](VALIDATION.md) §E3).
3. **E4** : implémenter l'attache par canal client et prouver l'alarme technique
   sur déconnexion dans `B_tech`.
4. **E1** : lire la norme payante et graver les bornes exactes.
5. **Matériel réel** : reproduire sur un vrai SoC QNX (ex. Raspberry Pi 5,
   `gcc_ntoaarch64le`) avec un capteur et un bus physiques.
6. **Clinique** : confronter la détection à un jeu annoté par un clinicien, et
   remplacer l'heuristique de pics R par un algorithme validé.