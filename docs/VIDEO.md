# Vidéo de soumission — storyboard et montage

Vidéo de démonstration **Veille** pour le QNX Global Hackathon 2026, catégorie
**Robotics & Medical**. Durée calée sur **2 min 40 s** (< 3 min). La narration
fait office de **sous-titres brûlés** dans l'image : elle est la source du
storyboard ci-dessous (`preuve/video/scenes.tsv`, source unique).

- **Captures** : `preuve/video/captures.sh` → `preuve/video/captures/*.txt` (sorties réelles de la cible QNX 8.0).
- **Diapositives** : `preuve/video/rendu.py` (Pillow) → `preuve/video/plans/*.png`.
- **Assemblage** : `preuve/video/montage.sh` (ffmpeg) → `preuve/video/veille.mp4`.

## Storyboard (2 min 40 s)

Ce tableau est généré par `python3 preuve/video/rendu.py --table` à partir de
`preuve/video/scenes.tsv` (une seule source, pas de copie à la main).

| # | Début | Fin | Image (capture à prendre) | Texte / voix-off | Ce que ça prouve |
|---|---|---|---|---|---|
| 1 | 0:00 | 0:12 | — (carton titre) | « Un moniteur patient QNX 8.0 dont la latence d'alarme, du capteur à l'alarme, est bornée… et prouvée, pas seulement mesurée. » | Le positionnement du projet. |
| 2 | 0:12 | 0:27 | — (carton) | « IEC 60601-1-8 fixe des délais ; IEC 62304 exige de les prouver. QNX donne le déterminisme, mais n'outille pas la preuve. » | Le trou que Veille comble. |
| 3 | 0:27 | 0:40 | — (carton) | « 4 800 états de défaillance explorés exhaustivement, vérifiés par deux implémentations indépendantes. » | La méthode (preuve ≠ mesure). |
| 4 | 0:40 | 0:55 | `captures/01-cible-uname.txt` | « QNX 8.0 tourne dans QEMU (image Quick Start, KVM) ; uname s'exécute dans l'invité. » | La cible est réelle. |
| 5 | 0:55 | 1:13 | `captures/02-demo-veille-sim.txt` | « veille-sim compilé avec le vrai qcc : 291 alarmes physiologiques, 8 techniques, L_measured ≤ B_proof. » | La chaîne tourne et prouve sur cible. |
| 6 | 1:13 | 1:31 | `captures/03-exploration-4800-etats.txt` | « Les 4 800 états explorés sur QNX : le contre-exemple bound=100 ms / latency=105 ms est retrouvé. » | L'exploration exhaustive tourne sur cible. |
| 7 | 1:31 | 1:53 | `captures/04-resmgr-4-issues.txt` | « Le resource manager valide les quatre issues : normal, tachycardie, capteur figé, capteur mort. » | `/dev/veille` est un vrai nœud QNX. |
| 8 | 1:53 | 2:15 | `captures/05-rejeu-ecg-mitdb-222.txt` | « MIT-BIH 222 rejoué sur cible : 2 500 pics R, 2 401 battements réels écrits dans /dev/veille. » | Des données de vrais patients, pas des synthétiques. |
| 9 | 2:15 | 2:27 | — (carton) | « E2 (priority inheritance), E3 (dérive du timer), E4 (disconnect canal) restent ouverts ; pas de matériel, pas de clinique. » | L'honnêteté : ce qui n'est pas démontré. |
| 10 | 2:27 | 2:35 | `captures/07-differentiel-hote-cible.txt` | « Le socle C11 et le jumeau Python sont deux implémentations séparées du même contrat. » | La double preuve. |
| 11 | 2:35 | 2:40 | — (carton) | « Dépôt, site, codelab, licence MIT ; dossier de preuve docs/QNX-EVIDENCE.md. » | L'appel à l'action. |

## Régénérer la vidéo

Prérequis : `ffmpeg` (assembleur) et `Pillow` (dessin des diapositives).

```bash
bash preuve/video/captures.sh   # 1. captures réelles sur la VM QNX 8.0 (VM allumée)
bash preuve/video/montage.sh    # 2. assemble preuve/video/veille.mp4 (H.264 1280x720, 30 i/s)
```

- Voix-off : déposer `preuve/video/voix-off.wav` (ou `.mp3`) ; sinon `montage.sh`
  produit une piste audio silencieuse (les sous-titres brûlés portent la narration).
- **Hors dépôt** : `preuve/video/veille.mp4` (vidéo) et `preuve/video/plans/*.png`
  (diapositives) sont ignorés par git (`.gitignore`). Seuls les scripts, le
  storyboard `scenes.tsv` et les **captures texte** `captures/*.txt` sont versionnés.
- Modifier un plan : éditer `preuve/video/scenes.tsv`, relancer `montage.sh`.