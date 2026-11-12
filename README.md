# Veille 🩺

## En 30 secondes

**Veille** est un **moniteur patient QNX 8.0** où la latence d'alarme
(*capteur → alarme*) est **bornée et prouvée** par exploration exhaustive de
**4800 états de défaillance** — au lieu d'être mesurée sur quelques scénarios
chanceux. La chaîne tourne sur un **QNX 8.0 réel** (QEMU/KVM), avec un jumeau
Python de vérification et un resource manager `/dev/veille`.

| Chiffre | Valeur |
|---|---|
| **4800** | états de défaillance explorés (sur cible, en 0,13 s) |
| **291 + 8** | alarmes physiologiques + techniques, `L_measured ≤ B_proof` |
| **2401** | battements réels (MIT-BIH) écrits dans `/dev/veille` sur la cible |
| **5** | défauts trouvés en passant sur la vraie cible, tous corrigés |

- **Vidéo** (2 min 40 s) : `preuve/video/veille.mp4` — [storyboard](docs/VIDEO.md)
- **Dossier de soumission** : [docs/SOUBMISSION.md](docs/SOUBMISSION.md)
- **Preuve** : [docs/QNX-EVIDENCE.md](docs/QNX-EVIDENCE.md) · [limites assumées](docs/LIMITS.md)

> *Un moniteur patient QNX 8.0 où la chaîne capteur→alarme a une latence **bornée et prouvée** par exploration exhaustive de tous les états de défaillance — au lieu d'être mesurée sur quelques scénarios chanceux.*

**Veille** est un framework de **garantie et de preuve de latence d'alarme médicale** sur QNX 8.0. Il traite la chaîne `acquisition (ECG/SpO2/PA) → filtrage → décision → alarme audible` comme un chemin critique à deadline, et **prouve** que la borne tient dans chaque état atteignable du système (capteur bloqué/mort/bruité, bus saturé, inversion de priorité, alarmes concurrentes, panne d'étage).

Projet candidat au **QNX Global Hackathon 2026** (dépôt le 15 décembre), catégorie **Robotics & Medical**, visant les bonus **Best use of QNX-specific Technologies** (message passing, priority inheritance, resource managers, pulses/timers, kernel trace) et **Best Codelab/Tutorial**.

---

## Pourquoi (les trous documentés)

- **IEC 60601-1-8** impose des caractéristiques temporelles d'alarme (délais, priorités, profils sonores). **IEC 62304** impose de les prouver.
- QNX SDP 8.0 fournit le déterminisme (priority inheritance `MsgSend`, pulses/timers, resource managers, kernel trace) mais **n'outille pas la preuve de latence d'alarme** : le System Profiler mesure des échantillons, il n'explore pas les états de défaillance ni ne certifie une borne pire-cas.
- Veille occupe exactement cet espace — comme **Ambre** prouve la durabilité du crash (UN R160), comme **Relais** prouve le failover à latence bornée (UN R79), comme **Tamis** prouve les politiques de sécurité.

## La promesse

Une alarme médicale passe d'« elle a sonné en test » à « **sa latence est garantie dans la borne B dans chaque état atteignable**, avec un certificat horodaté et empreinté (SHA-256) exploitable dans un dossier IEC 62304 ».

## Trois idées

1. **L'alarme est un chemin critique à deadline.** Latence de bout en bout `L = t(alarm) - t(sample)`, avec borne par priorité (haute 100 ms, moyenne 500 ms, basse 1000 ms, technique 50 ms).
2. **Preuve par exploration exhaustive, pas par mesure.** Tous les états de défaillance sont énumérés ( automate fini ), la borne est vérifiée dans chacun, ou un contre-exemple rejouable est produit.
3. **Double preuve.** Exhaustive (modèle d'états en C11 pur + jumeau Python) **et** empirique (kernel trace `tracelogger` sur cible QNX : `L_measured ≤ B_proof`).

## État

| Élément | État |
|---|---|
| Contrat gelé (`CONTRACT.md` v0.2) | ✅ 10 verdicts, formats texte/JSON/Markdown, API C, bornes tech |
| Cahier des charges (`VEILLE-cahier-des-charges.md`) | ✅ complet (15 sections) |
| Socle verdicts + rapports (`core/`) | ✅ compile `-Werror`, 6 objets |
| Jumeau Python (`host/`) | ✅ 6 tests unitaires verts |
| Exploration exhaustive complète (C4) | ✅ **4800 états** (5×3×2×5×32), P1 + P2, < 10 ms |
| Différentiel C↔Python | ✅ vert (4800 états, latence 105 ms des deux côtés) |
| Scénarios de référence | ✅ 4 JSON (nominal, sûr, moyen, violation P2) |
| Simulation hôte portable (`target/sim`) | ✅ `make demo` : 291 alarmes + 8 techniques, double preuve cohérente |
| Resource manager QNX (`target/rm`) | ✅ **exécuté sur cible QNX 8.0** : `/dev/veille` (4 issues de la chaîne validées), 5 défauts trouvés et corrigés — [preuve](docs/QNX-EVIDENCE.md) |
| Compilation croisée QNX 8.0 | ✅ `make qnx` avec le vrai qcc (SDP 8.0, cible `gcc_ntox86_64`) — [recette](docs/QNX-BUILD.md) |
| Exécution sur cible QNX 8.0 | ✅ émulateur QEMU (image Quick Start, KVM) : démo C identique à l'hôte, exploration des **4800 états sur cible** (0,13 s), resource manager validé |
| Données réelles (PhysioNet) | ✅ MIT-BIH (ECG + arythmies), BIDMC (ECG + PLETH/SpO2), slpdb (pression artérielle) — accès libre, ODC-By v1.0, [provenance](docs/REAL-DATA.md) |
| Rejeu de données réelles dans la chaîne | ✅ ECG de patients réels rejoués **dans l'émulateur QNX** ; 2401 bpm réels écrits dans `/dev/veille` |
| Codelab (4 chapitres + sommaire) | ✅ `codelab/` — bonus Best Codelab/Tutorial |
| Dossier de soumission (pitch, chiffres, questions jury) | ✅ [`docs/SOUBMISSION.md`](docs/SOUBMISSION.md) |
| Vidéo (storyboard + captures réelles + montage) | ✅ [`docs/VIDEO.md`](docs/VIDEO.md) — 8 captures sur cible, montage reproductible |
| Limites de la preuve assumées | ✅ [`docs/LIMITS.md`](docs/LIMITS.md) — E2/E3/E4, émulateur, statut non clinique |
| Docs sûreté | ✅ `SAFETY.md`, `GAP.md`, `DECISIONS.md`, `VALIDATION.md` |

## Build et test

Aucune dépendance à installer : `gcc` (C11) et `python3` (standard) suffisent.
**Tout tourne sans QNX, sans QEMU, sans licence** — la cible QNX est un plus, pas un prérequis.

```
make test       # construit et lance tous les tests (C + Python + différentiel)
make demo       # simulation hôte : chaîne capteur→alarme + double preuve (modèle + mesure)
make sanitize   # relance les tests C sous ASan/UBSan
make proof      # exploration exhaustive d'un sous-ensemble d'états (S4)
make lint       # garde taille fichiers (<500 lignes) et fonctions (<50 lignes)
```

## Architecture

```
veille/
├── CONTRACT.md              # source de vérité (gelé)
├── VEILLE-cahier-des-charges.md
├── core/                    # C11 pur : ni horloge, ni fichier, ni socket
│   ├── include/veille/      #   verdict.h chain.h state.h alarm.h proof.h report.h
│   ├── src/                 #   verdict.c chain.c state.c alarm.c proof.c report.c
│   └── tests/
├── host/                    # Python 3 stdlib : jumeau indépendant + CLI
├── target/                  # QNX 8.0 : resource manager /dev/veille, capteurs sim, kernel trace
├── scenarios/               # corpus de scénarios de défaillance
├── tests/                   # différentiel C↔Python, exploration, fault injection
├── codelab/                 # « prouver la latence d'une alarme médicale sur QNX »
└── docs/                    # SAFETY.md GAP.md DECISIONS.md VALIDATION.md IEC60601-8.md
```

**Jumeau de vérification** : `core/` (C11 pur) et `host/` (Python stdlib) sont deux implémentations **séparées** du même contrat. Le désaccord C↔Python est un bug, réduit dichotomiquement. Comme sur Ambre, Passerelle et Tamis.

## CI & socle self-hosted

Ce dépôt démarre sur le **socle CI self-hosted** (R630) : 3 workers `r630-veille-01..03` (label `veille-worker`), garde **`ci-budget`** (budget CI ≤ 5 min, règle user 2026-10-24), gate **hermes-lite** en dry-run, **Mergify** (file de merge, rebase, labels `urgent`/`priority-low`), **stale-base-guard**. La CI du projet (`build-test`) exige `ci-budget` + `build-test` verts pour entrer dans la file Mergify. Détail : [`docs/SOCLE-CI.md`](docs/SOCLE-CI.md).

## Sur cible QNX 8.0

Le projet n'est pas un prototype « pour Linux » : il **compile et s'exécute sur QNX 8.0**.

- **Compilation** : `make qnx` utilise le vrai `qcc` du SDP 8.0 (cible `gcc_ntox86_64`) et produit `veille-sim` et `veille-rm` (ELF QNX x86_64). Recette : [`docs/QNX-BUILD.md`](docs/QNX-BUILD.md).
- **Exécution** : sur l'image QNX Everywhere Quick Start Target Image (QEMU/KVM), la démo C donne le **même bilan que sur l'hôte** (291 alarmes physiologiques, 8 techniques, `L_measured ≤ B_proof`), l'exploration des **4800 états** s'exécute sur cible (0,13 s), et le resource manager `/dev/veille` valide les quatre issues de la chaîne (normal, tachycardie, capteur figé, capteur mort).
- **Données réelles** : des ECG de patients réels (PhysioNet) sont rejoués **dans l'émulateur** — 2401 battements réels écrits dans `/dev/veille` par le resource manager QNX.
- **Honnêteté** : les essais E2 (priority inheritance par kernel trace), E3 (cadence du timer) et E4 (CHANNEL disconnect) sont **déclarés non démontrés**, avec la cause exacte de chacun : [`docs/QNX-EVIDENCE.md`](docs/QNX-EVIDENCE.md). Journaux bruts : [`preuve/qnx80/`](preuve/qnx80/).

## Site

Tout le projet est visible dans un navigateur : **<https://tradoooo.github.io/veille/>** — accueil (pitch, chiffres clés calculés depuis le dépôt, état), cahier des charges, contrat gelé, codelab, code source (volumétrie, API C/Python), preuves (sorties de commande réellement exécutées à la génération), **preuve sur cible QNX 8.0**, recette de compilation croisée, données réelles et socle CI. Site statique en français, sans dépendance externe, construit et publié par GitHub Pages (`.github/workflows/pages.yml`).

Génération locale :

```
pip install 'markdown==3.5.2'          # unique dépendance, épinglée
python3 site/build.py /tmp/veille-site # puis ouvrir /tmp/veille-site/index.html
```

## Licence

MIT — voir [LICENSE](LICENSE).

## Projets frères (QNX Global Hackathon 2026)

- **Ambre** — EDR automotive, durabilité du crash prouvée (UN R160)
- **Relais** — failover steer-by-wire à latence bornée (UN R79)
- **Tamis** — analyse statique et preuve des politiques de sécurité `secpol`
- **Passerelle** — dossier partagé hôte-invité QEMU (virtio/9P/virtiofs)
- **Glane** — couche capteurs et publication de périphériques
- **Éclat** — WAMR + courtier de capacités
