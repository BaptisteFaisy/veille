# Veille — 100 idées pour consolider (avant le 15/12/2026 14 h ET)

Contexte réel au 12/11/2026 soir : le projet **tourne sur QNX 8.0** (émulateur, image
Quick Start Target Image, KVM), le **resource manager `/dev/veille`** est validé sur
cible, des **ECG de patients réels** (PhysioNet) sont rejoués dans la chaîne, et la
preuve est publiée (`docs/QNX-EVIDENCE.md`, `preuve/qnx80/`). Les essais **E2, E3, E4**
ne sont pas démontrés.

Échelle d'effort : **S** = quelques heures · **M** = ½ à 1 journée · **L** = plus d'une journée.
Impact : ★★★ = change la note · ★★ = renforce · ★ = confort.

---

## A. Sémantique & robustesse de la chaîne (le talon d'Achille connu)

| # | Idée | E | I |
|---|---|---|---|
| A1 | Détecter « capteur figé » sur le **signal brut** (variance, plateau) et non sur le bpm dérivé : corrige le faux positif constaté en fibrillation atriale | M | ★★★ |
| A2 | Hystérésis sur les seuils (±10 %) : l'alarme ne doit pas osciller autour du seuil | S | ★★ |
| A3 | Implémenter les 5 états capteur du cahier : `ok`, `stuck`, `dead`, `noisy`, `drift` (aujourd'hui 3) | M | ★★★ |
| A4 | Médiane au lieu de moyenne pour la fréquence cardiaque : robuste aux extrasystoles | S | ★★ |
| A5 | Séparer explicitement alarme **physiologique** et alarme **technique** dans le rapport d'audit (canaux distincts) | S | ★★ |
| A6 | Priorités d'alarme haute/moyenne/basse + escalade si l'alarme n'est pas acquittée (IEC 60601-1-8) | M | ★★★ |
| A7 | Verrouillage (« lock ») et acquittement avec le délai `B_ack` (60 s) réellement appliqués | M | ★★ |
| A8 | Journal d'alarmes durable sur `/data` : la trace des alarmes passées (traçabilité IEC 62304) | M | ★★★ |
| A9 | Reprise après redémarrage : l'état de la chaîne et le journal survivent au reboot | M | ★★ |
| A10 | Détecter la dérive temporelle (horloge monotone vs horloge murale) et dater chaque événement | S | ★ |

## B. Preuves et exploration

| # | Idée | E | I |
|---|---|---|---|
| B1 | Élargir l'espace d'états (ajouter bruit, dérive, perte réseau) et prouver P1…P5 | M | ★★★ |
| B2 | Prouver P3 : « l'alarme technique ne dépasse jamais B_tech » | S | ★★★ |
| B3 | Contre-exemple **minimal** rejouable + le chemin fautif (réduction dichotomique) | M | ★★ |
| B4 | Preuve d'exploration **sur cible** : 4800 états sur QNX, temps mesuré + empreinte du binaire | S | ★★ |
| B5 | Couverture de tests (gcov) et liste des branches non couvertes | S | ★★ |
| B6 | Mutation testing des 10 verdicts : chaque mutant doit être tué | M | ★★★ |
| B7 | Propriété de monotonie : plus de charge ne peut pas **diminuer** la latence mesurée (fuzz) | M | ★★ |
| B8 | Fuzz sous charge : aucune inversion de priorité (E2 par le comportement) | M | ★★★ |
| B9 | Rapport de preuve versionné et signé (SHA-256 config + binaire + trace) | S | ★★ |
| B10 | Propriété « aucune alarme physiologique sur les 48 enregistrements MIT-BIH » (mesurée, pas affirmée) | M | ★★★ |

## C. Intégration QNX native (le cœur du prix « Best use of QNX technologies »)

| # | Idée | E | I |
|---|---|---|---|
| C1 | **E2 comportemental** : client SCHED_FIFO 63 bloqué sur le rm à 62 → mesurer le temps d'attente (l'héritage de priorité se voit sans kernel trace) | M | ★★★ |
| C2 | **E3 mesuré** : dérive de la cadence `timer_create`+`SIGEV_PULSE` au repos et sous charge (publish the numbers) | S | ★★★ |
| C3 | **E4 par watchdog** : « silence du capteur > X ms » → alarme technique (mécanisme médicalement juste, implémentable avec un timer) | M | ★★★ |
| C4 | Notification de disconnect **par canal client** (le vrai mécanisme) au lieu du dispatch | M | ★★ |
| C5 | Adaptive partitioning : partition critique (alarme) isolée de la partition best-effort (traitement) → montrer l'isolation | M | ★★★ |
| C6 | `secpol` : cloisonner les clients du rm (abilities par fichier), publié et vérifié | M | ★★ |
| C7 | `procmgr_ability` : le rm n'accepte que les clients porteurs de l'ability requise | S | ★★ |
| C8 | devctl sur le rm : configurer mode/bornes/seuils par requête typée (au lieu du texte) | S | ★★ |
| C9 | io-sock : publier les verdicts en MQTT/AMQP vers un superviseur (démo live, « Best use of QNX ») | M | ★★★ |
| C10 | `dumper` : capturer l'état du rm au crash et le rejouer au démarrage | M | ★★ |
| C11 | `pidin`/`hogs` : métriques live (échantillons/s, alarmes/s) publiées sur le site | S | ★★ |
| C12 | Timeline « trace » reconstruite depuis nos horodatages (sans l'outil noyau) → page web | M | ★★ |

## D. Données réelles

| # | Idée | E | I |
|---|---|---|---|
| D1 | Parser les annotations `.atr` (vérité terrain MIT-BIH) | M | ★★★ |
| D2 | **Score de détection** sensibilité/spécificité du détecteur de pics R sur les 48 enregistrements MIT-BIH (chiffre qui vaut de l'or devant un jury médical) | M | ★★★ |
| D3 | Score d'alarme : le seuil de 120 bpm détecte-t-il les vraies arythmies ? (VP vs FA) | M | ★★★ |
| D4 | PLETH BIDMC → SpO2 réel en continu + alarme de désaturation (priorité moyenne) | M | ★★★ |
| D5 | Pression artérielle réelle (slpdb) → alarmes hypo/hyper-tension, bornes dédiées | M | ★★ |
| D6 | Injection de fautes **dans le signal ECG réel** (drop-out, drift, bruit) → la détection est-elle prouvée sur données corrompues ? | M | ★★★ |
| D7 | Rejeu en cadence réelle (horloge murale) sur cible, latence mesurée par l'horloge noyau | S | ★★ |
| D8 | Jeu de données supplémentaire en accès libre (CapnoBASE pour la respiration) | S | ★ |
| D9 | MIMIC-IV-Waveform (PPG/SpO2) si l'accès se libère | L | ★★ |
| D10 | Corpus d'arythmies annoté **versionné** (liste d'ID + empreintes) dans le dépôt | S | ★★ |

## E. Démonstration, vidéo, jury

| # | Idée | E | I |
|---|---|---|---|
| E1 | **Vidéo < 3 min** : storyboard plan par plan, captures réelles (console QNX comprise) | M | ★★★ |
| E2 | Scène animée du rejeu réel (ECG qui défile, alarme, verdict, latence) sur le site | M | ★★★ |
| E3 | Rejouer une session QNX capturée dans le navigateur (hors-ligne, reproductible) | M | ★★ |
| E4 | Mode « démo » : le site interroge la VM en direct (latences, alarmes/s) | M | ★★ |
| E5 | Page « avant/après » : ECG synthétique vs ECG de patient réel | S | ★★ |
| E6 | README en 30 secondes : pitch, 3 chiffres, lien vidéo, preuve | S | ★★★ |
| E7 | Devpost : 3 captures, 1 vidéo, réponses préparées aux 6 questions attendues | M | ★★★ |
| E8 | One-pager PDF généré depuis le dépôt (zéro copier-coller) | S | ★★ |
| E9 | FAQ « et si c'était un faux positif ? » avec la réponse mesurée | S | ★★ |
| E10 | Son d'alarme réel : profils sonores IEC 60601-1-8 synthétisés sur cible | S | ★★ |

## F. Codelab & documentation

| # | Idée | E | I |
|---|---|---|---|
| F1 | Chapitre « écrire un resource manager QNX 8 qui publie un verdict » (le vrai code) | M | ★★★ |
| F2 | Chapitre « priority inheritance et pulses : ce que le noyau fait vraiment » | M | ★★★ |
| F3 | Chapitre « rejouer des données cliniques réelles sur une cible QNX » | M | ★★ |
| F4 | Exercices vérifiables automatiquement (scripts qui lancent les commandes sur la VM) | M | ★★ |
| F5 | Glossaire IEC 60601-1-8 ↔ la chaîne (vocabulaire médical dans la langue du jury) | S | ★★ |
| F6 | « Anatomie d'un verdict » : du pixel brut au verdict, chaque étape pointée dans le code | M | ★★★ |
| F7 | Diagramme d'architecture généré depuis le code (SVG, jamais dessiné à la main) | S | ★★ |
| F8 | ADR : les décisions de conception et leur « pourquoi » reliés depuis le README | S | ★ |
| F9 | Pages clés en anglais (jury international) | S | ★★ |
| F10 | Chaîne de preuve narrative : « voici la propriété, voici comment on l'a prouvée, voici le journal » | S | ★★★ |

## G. Qualité & industrialisation

| # | Idée | E | I |
|---|---|---|---|
| G1 | **CI avec le SDP sur le runner r630** (le SDP y est déjà copié) → build QNX reproductible par le jury | S | ★★★ |
| G2 | Smoke test « la VM démarre et répond » dans la CI (QEMU + KVM sur le runner) | M | ★★★ |
| G3 | ASan/UBSan **sur cible QNX** (le SDP les fournit) | S | ★★ |
| G4 | Fuzzing du parseur WFDB (formats 212/16) — cible de fuzz quasi idéale | M | ★★ |
| G5 | Fuzzing du parseur d'annotations `.atr` | M | ★★ |
| G6 | Golden files : le format texte du rapport est un contrat, on le fige | S | ★★ |
| G7 | `make qnx && make run-qnx` : la démo tient en deux commandes | S | ★★★ |
| G8 | Versionnement sémantique + CHANGELOG | S | ★ |
| G9 | Durcissement : `-Werror`, `-D_FORTIFY_SOURCE`, sanitizers en CI | S | ★★ |
| G10 | SBOM / CycloneDX pour la conformité | S | ★ |

## H. Observabilité & exploitation

| # | Idée | E | I |
|---|---|---|---|
| H1 | Journal structuré JSONL du rm (verdicts horodatés par l'horloge noyau) | S | ★★ |
| H2 | Métriques : échantillons/s, latence p50/p99/max, alarmes/s, taux de faux positifs | M | ★★★ |
| H3 | Trace distribuée : un `traceid` par échantillon, de l'acquisition au rapport | M | ★★ |
| H4 | « Flight recorder » : anneau des 10 000 derniers verdicts | S | ★★ |
| H5 | La page « preuves » se régénère à chaque commit (CI qui publie les sorties réelles) | M | ★★ |
| H6 | Alerte externe sur alarme technique (MQTT/Telegram) pour la démo live | S | ★★ |
| H7 | Supervision : `hogs`/`pidin` dans le rapport de session | S | ★ |

## I. Produit & usage

| # | Idée | E | I |
|---|---|---|---|
| I1 | « Patient virtuel » : un banc qui injecte des scénarios et note les verdicts | M | ★★ |
| I2 | Bornes paramétrables par protocole (le moniteur s'adapte au protocole clinique) | S | ★★ |
| I3 | Multi-capteur : ECG + SpO2 + PA, fusion des verdicts (priorité max) | M | ★★★ |
| I4 | Rapport d'audit IEC 62304 imprimable (Markdown → PDF) | S | ★★ |
| I5 | Matrice exigence → test → preuve auto-générée (le rêve de l'auditeur) | S | ★★★ |
| I6 | Mode économie d'énergie : le rm veille, réveil sur événement | M | ★ |
| I7 | Réseau interrompu → alarme technique bornée (le moniteur ne reste pas muet) | M | ★★ |
| I8 | Signature du rapport de preuve (HMAC) | S | ★ |

## J. Risque, honnêteté, jury

| # | Idée | E | I |
|---|---|---|---|
| J1 | Document « la preuve par exploration est-elle une preuve ? » : hypothèses, limites, ce que ça ne dit pas | S | ★★★ |
| J2 | Baseline honnête : le surcoût de la garantie face à un simple seuil (mesuré) | M | ★★ |
| J3 | Étude de cas : 3 patients simulés × 3 scénarios d'alarme | M | ★★ |
| J4 | « Que se passe-t-il si le capteur ment ? » : corruption, dérive, drop-out — robustesse mesurée | M | ★★★ |
| J5 | Traçabilité complète des exigences du cahier → test → preuve | M | ★★★ |
| J6 | Roadmap post-soumission (open source, QNX 8.0, contributions amont) | S | ★★ |

---

## Les 10 meilleures, dans l'ordre d'exécution

1. **A1 — le « capteur figé » détecté sur le signal brut** (M, ★★★). C'est le défaut
   connu, observé en fibrillation atriale : le bpm arrondi reste identique deux
   échantillons d'affilée → fausse alarme technique au lieu de l'alarme
   tachycardie. Corrigé, la demo raconte la vérité ; non corrigé, un juge qui
   regarde les données s'en aperçoit. *Critère d'acceptation* : sur MIT-BIH 222 et
   205, plus aucune alarme « capteur figé » pendant les épisodes tachycardiques,
   tout en gardant la détection d'un vrai signal plat.
2. **D2/D3 — le score de détection sur la vérité terrain MIT-BIH** (M, ★★★).
   Parser les `.atr`, mesurer sensibilité/spécificité du détecteur de pics R et
   justesse des alarmes sur les 48 enregistrements. Un chiffre mesuré (« 92 % de
   sensibilité, 0 faux positif sur 48 enregistrements ») vaut dix affirmations.
3. **E1 — la vidéo < 3 min** (M, ★★★). Sans vidéo, la note plafonne. Scénario :
   boot QNX 8.0 → rejeu d'un ECG réel → alarme → verdict + latence → preuve
   d'exploration → limites assumées. Captures réelles (console série comprise).
4. **C1/C2 — E2 et E3 démontrés par la mesure** (M, ★★★). E3 : dérive de la
   cadence du tick au repos et sous charge. E2 : l'héritage de priorité se
   mesure par le temps d'attente d'un client SCHED_FIFO 63 face à un rm à 62 —
   pas besoin du kernel trace, donc pas bloqué par l'incompatibilité `traceprinter`.
5. **H2/A1 — les latences réelles sous charge** (M, ★★★). Aujourd'hui : « 0,001 ms »
   en simulation. Mesurer p50/p99/max sur cible, au repos et sous charge, avec un
   client qui inonde le rm. C'est le cœur de la promesse (« latence bornée »).
6. **C5 — adaptive partitioning** (M, ★★★). Deux partitions : l'alarme critique
   isolée du traitement best-effort. Démo : le traitement sature, l'alarme reste
   dans sa borne. Un argument « Best use of QNX » difficile à réfuter.
7. **E2/F1 — la scène animée + le chapitre de codelab sur le resource manager**
   (M, ★★★). La scène (même esprit que la page Ambre) rend le rejeu réel
   visible ; le chapitre montre comment le resource manager a été écrit. Bonus
   « Best Codelab/Tutorial » visé.
8. **G1 — la CI qui compile pour QNX** (S, ★★★). Le SDP est déjà copié sur le
   runner r630 : `make qnx` en CI, sous le budget de 5 min. Le jury peut
   reproduire la compilation en une commande.
9. **I5/J5 — la matrice exigence → test → preuve** (S, ★★★). Les tableaux des
   cahiers existent déjà : il faut les croiser avec les tests et les journaux.
   Trame idéale pour un auditeur IEC 62304.
10. **J1/J4 + E6/E7 — l'honnêteté comme argument** (S, ★★★). Un paragraphe qui
    dit ce que la preuve ne démontre pas (E2/E3/E4, matériel réel, patients
    différents), le README en 30 secondes, les 6 questions Devpost préparées.

## Plan sur les 3 jours restants (dépôt 15/12 14 h ET)

- **Mer. 12 soir – jeu. 13 matin** : A1, C1, C2, H2 (le cœur technique), puis D1/D2.
- **Jeu. 13 – ven. 14 matin** : D2/D3 chiffrés, C5 (partitions), E2 (scène),
  F1/F6 (codelab), G1 (CI SDP), I5 (matrice).
- **Ven. 14 après-midi – sam. 15 matin** : E1 (vidéo), E6/E7 (README + Devpost),
  J1/J4 (limites), relecture, gel du dépôt à 10 h.
- **À surveiller** : la file Mergify se bloque quand une branche n'est pas
  rebasée (`git rebase origin/main` + `push --force-with-lease` débloque) ; le
  `traceprinter` du SDP installé ne lit pas les traces de l'image (E2 par le
  kernel trace reste bloqué tant qu'on n'a pas un SDP de septembre 2026).
