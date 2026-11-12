# Preuve en images — Veille sur QNX 8.0 (émulateur)

Captures d'écran de la **console série de l'émulateur QEMU** (où tourne QNX 8.0),
prises **toutes les 2 secondes** pendant une démonstration, puis rendues en PNG
et montées en timelapse.

## Contenu

| Fichier | Ce qu'il montre |
|---|---|
| `1-uname-qnx80.png` | `uname -a` → `QNX qnxqemu 8.0.0 2026/06/05 x86pc x86_64` |
| `2-resmgr-demarre.png` | le resource manager `/dev/veille` démarré (`--no-tick`), le nœud `/dev/veille` créé |
| `3-quatre-issues.png` | la chaîne validée sur cible : normal → OK, tachycardie → alarme haute, capteur figé/mort → alarme technique |
| `4-ecg-reel-mitdb222.png` | rejeu d'un **ECG réel** (MIT-BIH 222, fibrillation atriale) dans `/dev/veille` : 2 500 pics R, 2 401 battements |
| `5-verdict-et-processus.png` | le verdict courant du resource manager + les processus QNX (`veille-rm`, `procnto-smp-instr`) |
| `planche-contact.png` | les 5 étapes ci-dessus + 5 captures automatiques, en une image |
| `proof-qnx.mp4` | **timelapse** des captures automatiques (toutes les 2 s) |

## Régénérer

```bash
# la VM QNX doit tourner (voir tools/qnx/boot.sh) ; puis :
python3 tools/qnx/console-proof.py /tmp/qnx-screens   # 51 PNG, une toutes les 2 s
ffmpeg -y -framerate 5 -pattern_type glob -i '/tmp/qnx-screens/auto-*.png' proof-qnx.mp4
```

La VM est pilotée par `/tmp/qnx-vm-gui.sh` (affichage VNC + console série TCP 4444
+ SSH 8022 + moniteur QEMU socket `/tmp/qemu-mon.sock` pour `screendump`).
