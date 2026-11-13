# image/ — l'invité QNX 8.0 de Veille

Cette image invitée fait tourner **le vrai cœur C de Veille dans QNX 8.0**
(x86_64), pas une simulation sur l'hôte. Elle sert à produire la preuve
« sur cible » : l'exploration exhaustive des 4 800 états, le gestionnaire de
ressources `/dev/veille` et un client qui mesure 200 allers-retours, tout cela
exécuté par l'invité.

| Fichier | Rôle |
|---|---|
| `buildfile` | description `mkifs` de l'IFS (noyau, libs, outils QNX, binaires Veille, `demo.sh`) |
| `build-image.sh` | orchestre `qcc` → `mkifs` → `mkxfs` → `diskimage` via le paquet `~/Bureau/qnx-emu` |
| `demo.sh` | le scénario joué au démarrage, sur la console VGA (et recopié sur la série) |

## Construire

Prérequis : le SDP QNX 8.0 (`~/qnx800`) et le paquet réutilisable
`~/Bureau/qnx-emu` (même chaîne que Réplique, Tamis, Glane, Toile, Ambre).

```sh
export QNX_SDP=$HOME/qnx800
sh image/build-image.sh                 # sortie par défaut : ~/veille-img
# ou : sh image/build-image.sh /chemin/de/sortie
```

La sortie contient `ifs.bin` (l'image, ~5,4 Mo), `veille-sim`, `veille-rm`,
`bench-client`, `demo.sh`, le disque `veille-disk.img` (pour la trace) et
`image.resolved` (le buildfile avec les chemins résolus).

## Démarrer

```sh
~/Bureau/qnx-emu/guest-qemu.sh \
    --ifs ~/veille-img/ifs.bin \
    --serie ~/veille-demo/serial.log \
    --moniteur ~/veille-demo/mon.sock \
    --memoire 1024 --cpu max --smp 2 \
    --qemu /usr/bin/qemu-system-x86_64 --prefixe ~/.qemu-data
```

Puis, pour voir l'écran et injecter des touches, la vitrine HTTP du paquet
`qnx-emu` (une seule implémentation pour tous les projets QNX 8.0) :

```sh
QNX_EMS_SERIE=~/veille-demo/serial.log QNX_EMS_MON=~/veille-demo/mon.sock \
QNX_EMS_PPM=~/veille-demo/web-vga.ppm QNX_EMS_PORT=8121 \
  python3 ~/Bureau/qnx-emu/web.py
#  GET /            page (écran + console + boutons)
#  GET /screen.png  capture VGA fraîche (screendump du moniteur)
#  GET /console     journal de la console série
#  GET /key?k=RET   sendkey dans l'invité
```

En service : `veille-qemu.service` + `veille-web.service` (unités utilisateur,
`systemctl --user enable --now …`), exposées en HTTPS par `tailscale funnel`.

## Ce que joue `demo.sh`

1. `veille-sim` — exploration exhaustive (`bound=200`, `states=4800`) puis
   simulation de 600 échantillons avec pannes injectées (alarmes
   physiologiques et techniques, latence mesurée contre la borne prouvée) ;
2. `veille-rm` — gestionnaire de ressources `/dev/veille` (pulses, timer
   noyau `CLOCK_MONOTONIC`, `MsgSend`) ;
3. `bench-client` — 200 allers-retours sur `/dev/veille` (min/max/moyenne),
   puis le verdict courant ; la déconnexion du client déclenche l'alarme
   technique « mort d'un pair » ;
4. état final : le rm est relancé, `/dev/veille` répond, l'invite reste
   interactive.

Le journal complet est recopié sur la console **série** (`cat $LOG > /dev/ser1`)
pour que la vitrine l'affiche en texte.

## Pièges QNX 8.0 réellement payés (chacun a coûté un cycle)

1. **`--cpu max` est obligatoire** : `qemu64` ne démarre pas l'invité.
2. **Le périphérique RNG virtio est obligatoire** :
   `-object rng-random,filename=/dev/urandom,id=rng0 -device virtio-rng-pci,rng=rng0`.
3. **L'IFS se lance par `-kernel`, pas par le disque** : en disque, le chargeur
   s'arrête sur « QNX v1.2d Boot Loader ».
4. **Sans disque, `/var` est un lien mort** : écrire dans `/dev/shmem`.
5. **QNX 8.0 n'embarque plus de coreutils** : `toybox` est multi-applets (un
   lien par applet) et **n'a pas d'applet `kill`** — utiliser `slay`.
6. **Le shell `[+script]` ne gère ni tubes ni redirections ni `$!`** : lancer le
   scénario par `on -d -t /dev/con1 … ksh -c /proc/boot/demo.sh`.
7. **Sans disque, ce `ksh` ne peut ni créer un tube ni faire une substitution
   de commande** : `demo.sh` n'utilise que des redirections par fichier.
8. **Aucun `printf` dans l'image** (ni builtin de ce ksh, ni applet lié) : le
   scénario écrit avec `echo`.
9. **La console VGA est orientée octet** (police CP437) : un octet UTF-8
   s'affiche en deux glyphes — tous les messages destinés à l'écran sont en
   ASCII (y compris ceux du resource manager, voir `target/rm/rm_chain.c`).
10. **`traceprinter` lit `/dev/shmem/tracebuffer.kev` par défaut** et échoue
    (« internal error code(12) ») : la forme correcte est `traceprinter -f trace.kev`.
    Et le SDP installé (janvier 2025) ne décode pas les traces de l'image
    (septembre 2026) — d'où la preuve E2 par mesure comportementale A/B.

## Ce que l'image ne démontre pas

- **Émulateur ≠ matériel** : les latences mesurées sont celles d'un invité
  sous QEMU, pas d'un cœur temps réel dédié.
- **Pas de bureau graphique** : l'image socle n'a pas de pilote d'affichage ;
  la « capture d'écran » est la console VGA texte (c'est le vrai terminal de
  l'invité).
- **E2 par trace noyau** : la trace est capturée et décodée, mais cette image
  n'expose aucun événement de changement de priorité ; la preuve d'héritage de
  priorité reste la mesure A/B (p95 ×82).