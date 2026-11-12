# Veille 🩺

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
| Resource manager QNX (`target/rm`) | 🚧 squelette documenté (`#ifdef __QNX__`), à valider sur QEMU (E2–E4) |
| Codelab (4 chapitres + sommaire) | ✅ `codelab/` — bonus Best Codelab/Tutorial |
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

## Site

Tout le projet est visible dans un navigateur : **<https://baptistefaisy.github.io/veille/>** — accueil (pitch, chiffres clés calculés depuis le dépôt, état), cahier des charges, contrat gelé, codelab, code source (volumétrie, API C/Python), preuves (sorties de commande réellement exécutées à la génération) et socle CI. Site statique en français, sans dépendance externe, construit et publié par GitHub Pages (`.github/workflows/pages.yml`).

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
