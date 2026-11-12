# Preuve vidéo — matrice des captures

Chaque ligne correspond à **un fichier réellement produit** par
[`captures.sh`](captures.sh) sur la cible **QNX 8.0** (émulateur QEMU, image
Quick Start). Les fichiers sont des sorties de commande brutes : l'en-tête
rappelle la commande exacte, l'`uname` de l'invité et le code de sortie.

Les captures sont **versionnées** (texte, quelques kilo-octets). La vidéo
assemblée (`veille.mp4`) et les diapositives (`plans/`) sont des artefacts
volumineux : ils sont **hors dépôt** et se régénèrent avec les commandes
ci-dessous.

| Capture | Commande qui la produit | Ce qu'elle prouve |
|---|---|---|
| `captures/01-cible-uname.txt` | `uname -a; pidin -F "%a %n"; ls -l /data/veille/veille-sim /data/veille/veille-rm` | La cible est un **QNX 8.0 réel** (`QNX qnxqemu 8.0.0 2026/06/05-16:26:03EDT x86pc x86_64`), avec `procnto` et les deux binaires QNX présents — pas un mock, pas l'hôte Linux. |
| `captures/02-demo-veille-sim.txt` | `cd /data/veille && ./veille-sim` | La **chaîne C tourne sur la cible** et rend le même bilan que sur l'hôte : 291 alarmes physiologiques, 8 alarmes techniques, `[OK] L_measured <= B_proof`. |
| `captures/03-exploration-4800-etats.txt` | `cd /data/veille-py && time python3 -m veille.cli proof` | L'**exploration exhaustive des 4800 états s'exécute sur QNX** et retrouve le contre-exemple attendu (`bound=100ms latency=105ms states=4800`). Le code de sortie 1 est le comportement correct d'une preuve qui échoue à dessein. Le temps mural dépend de la charge de l'invité (0,13 s au repos, ≈ 2,8 s ici) — le verdict, lui, ne change pas. |
| `captures/04-resmgr-4-issues.txt` | `sh /data/veille/rm-restart.sh --no-tick` puis `sh /data/veille/rm-test.sh` | Le **resource manager `/dev/veille`** est un vrai nœud QNX : les quatre issues de la chaîne rendent les quatre verdicts attendus (normal, tachycardie, capteur figé, capteur mort). |
| `captures/05-rejeu-ecg-mitdb-222.txt` | `cd /data/veille-py && time python3 -m veille.resmgr_client --record /data/veille-data/mitdb/222 --signal MLII --sortie /dev/veille` | **2401 battements réels** (MIT-BIH 222, fibrillation atriale) sont écrits dans `/dev/veille` sur la cible : 2500 pics R détectés, bpm 43 → 181,5, moyenne 87,9. |
| `captures/06-rejeu-ecg-mitdb-100.txt` | `cd /data/veille-py && time python3 -m veille.resmgr_client --record /data/veille-data/mitdb/100 --signal MLII --sortie /dev/veille` | **Controle** sur un enregistrement réel en rythme sinusal normal (MIT-BIH 100) : 2271 battements écrits, bpm 61 → 89,6, aucune alarme haute — la chaîne ne crie pas sur un signal normal. |
| `captures/07-differentiel-hote-cible.txt` | `make demo` (poste de travail) | Le **même bilan sur l'hôte** : la chaîne C ne se comporte pas autrement sous QNX — c'est la comparaison différentielle. |
| `captures/08-serial-console.txt` | `python3 /tmp/qnx-console.py 4444 6 'uname -a' 'pidin -F "%p %n" \| grep [v]eille-rm'` | La cible répond **aussi sur la console série** (port 4444), avec le resource manager `veille-rm` vivant dans la liste des processus. |

## Régénérer

```bash
bash preuve/video/captures.sh   # produit les 8 captures ci-dessus (VM QNX allumée)
bash preuve/video/montage.sh    # assemble veille.mp4 (2 min 40 s, H.264 1280x720)
```

## Ajouter une voix-off

Déposer `preuve/video/voix-off.wav` (ou `.mp3`) : `montage.sh` la muxera
automatiquement à la place de la piste silencieuse. Les sous-titres brûlés dans
l'image portent déjà la narration plan par plan (`proof/video/scenes.tsv`).
