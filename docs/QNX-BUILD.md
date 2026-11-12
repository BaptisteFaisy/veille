# Build QNX 8.0 — recette reproductible (`make qnx`)

Statut : **compilation croisée vérifiée sur l'hôte** (binaires ELF QNX/x86-64
produits). **Rien n'a encore tourné sur cible** : l'exécution dans l'émulateur
QNX (QEMU) est une étape distincte et pilotée séparément. Aucun résultat E2/E3/E4
du cahier des charges n'est revendiqué comme testé ici (voir §5).

## 1. SDP utilisé

- Installation : `/home/baptiste/qnx800` (hôte `host/linux/x86_64`, cibles
  `target/qnx/x86_64` et `aarch64le`).
- Version noyau/SDP — `target/qnx/usr/include/sys/nto_version.h` (les en-têtes
  sont partagés dans `target/qnx/usr/include`, pas dans `target/qnx/x86_64/`) :

```c
#define _NTO_VERSION	800	/* version number * 100 */
#define _NTO_KERNEL_VERSION_MAJOR 2
#define _NTO_KERNEL_VERSION_MINOR 6
#define _NTO_KERNEL_VERSION_PATCH 0
```

- `qcc -V` (après sourçage de l'environnement, §2) :

```text
cc: targets available in /home/baptiste/qnx800/host/linux/x86_64/etc/qcc:
	12.2.0,gcc_ntoaarch64le_cxx
	12.2.0,gcc_ntoaarch64le
	12.2.0,gcc_ntox86_64	(default)
	12.2.0,gcc_ntox86_64_gpp
	12.2.0,gcc_ntoaarch64le_gpp
	12.2.0,gcc_ntox86_64_cxx
```

La cible retenue est donc **`gcc_ntox86_64`** (GCC 12.2.0) — et non
`gcc_nto/x86_64le` ni `nto x86_64le`, qui ne figurent pas parmi les cibles
annoncées par ce SDP. Pour RPi5 : `QCC_V=gcc_ntoaarch64le`.

## 2. Environnement

`qnxsdp-env.sh` doit être **sourcé depuis bash** (il refuse d'être exécuté et
teste `BASH_SOURCE`) ; il pose `QNX_HOST`, `QNX_TARGET` et le `PATH` :

```bash
source /home/baptiste/qnx800/qnxsdp-env.sh
```

## 3. Commande de build

```bash
make qnx                                   # x86_64 (défaut)
make qnx QCC_V=gcc_ntoaarch64le QNX_DIR=build/qnx-aarch64   # RPi5
make qnx QNX_SDP=/chemin/vers/sdp          # autre installation du SDP
```

Drapeaux (Makefile, section `qnx`) :

```text
qcc -V gcc_ntox86_64 -std=c11 -O2 -Wall -Wextra -Werror -D_QNX_SOURCE \
    -Icore/include -Itarget/pipe -Itarget/port -Itarget/rm
```

Choix documentés :

- **Pas de `-D__QNX__` explicite** : qcc 8.0 **pré-définit `__QNX__=800`**
  (vérifié : `echo | qcc -V gcc_ntox86_64 -dM -E - | grep __QNX`). Un
  `-D__QNX__` nu définit la macro à `1` → conflit de redéfinition → échec avec
  `-Werror`. L'intention du contrat de build (`__QNX__` défini) est donc remplie
  par le compilateur lui-même.
- **`-D_QNX_SOURCE`** : en `-std=c11` strict (`__STRICT_ANSI__`), les en-têtes
  QNX masquent POSIX-2001 et les extensions QNX. `_QNX_SOURCE` active
  `__EXT_POSIX1_200112` (`timer_create`, `timer_settime`, `CLOCK_MONOTONIC`)
  **et** `__EXT_QNX` (`SIGEV_PULSE_INIT`, `SETIOV`, `_PULSE_CODE_*`) — voir
  `sys/platform.h`. `_POSIX_C_SOURCE 199309L` ne suffit PAS sur QNX
  (`CLOCK_MONOTONIC` exige 200112, contrairement à glibc).

## 4. Ce qui compile, et comment c'est organisé

Sorties dans `build/qnx/` (gitignoré via `build/`) :

| Binaire       | Sources                                                                                       | Rôle |
|---------------|-----------------------------------------------------------------------------------------------|------|
| `veille-sim`  | `core/src/*.c` + `target/pipe/veille_pipe.c` + `target/port/qnx_time.c` + `target/sim/sim.c`  | la démo `make demo`, version QNX (mêmes échantillons, mêmes pannes injectées, double preuve) |
| `veille-rm`   | `core/src/*.c` + `target/pipe/` + `target/port/qnx_time.c` + `target/rm/{rm_chain,rm_io,resmgr_veille}.c` | resource manager `/dev/veille` |

Zéro duplication hôte/QNX :

- `target/pipe/veille_pipe.[ch]` — pipeline portable acquire→filter→decide,
  **partagé à l'identique** par la sim hôte, la sim QNX et le resmgr (extrait de
  `sim.c` ; comportement hôte vérifié inchangé, sortie de `make demo` identique).
- `target/port/port_time.h` + `host_time.c` / `qnx_time.c` — la seule divergence
  hôte/cible (l'horloge monotone ; `core/` reste pur) est isolée dans deux petits
  fichiers d'implémentation, aucun `#ifdef` dispersé.

Vérification des binaires produits (`file build/qnx/*`) :

```text
build/qnx/veille-sim: ELF 64-bit LSB pie executable, x86-64, version 1 (SYSV), dynamically linked, interpreter /usr/lib/ldqnx-64.so.2, BuildID[md5/uuid]=de72ae65ae122e7ef56fc960d7a7d883, with debug_info, not stripped
build/qnx/veille-rm:  ELF 64-bit LSB pie executable, x86-64, version 1 (SYSV), dynamically linked, interpreter /usr/lib/ldqnx-64.so.2, BuildID[md5/uuid]=c5e1412f3e59c9c08a1ea31128dcde7b, with debug_info, not stripped
```

## 5. Ce qui reste À VALIDER SUR CIBLE (honnêteté stricte)

Rien de ce qui suit n'a tourné dans l'émulateur ; ce ne sont que des intentions
câblées dans le code, à démontrer sur cible (cahier des charges E2/E3/E4) :

- **E2 — priority inheritance observable par kernel trace** : `veille-rm` place
  son fil en `SCHED_FIFO 62` (`setup_priority()`), censé propager la priorité
  aux clients `MsgSend` ; à vérifier avec `tracelogger`/kernel trace que le sink
  tourne bien à la priorité de l'appelant pendant le message, et que
  `L_measured <= B_proof` sur la trace.
- **E3 — cadence `timer_create` + pulse** : le tick 10 ms par
  `timer_create(CLOCK_MONOTONIC)` + `SIGEV_PULSE_INIT` → `pulse_attach` est
  compilé mais **non exécuté** ; la dérive de cadence et la latence
  pulse→traitement restent à mesurer sur cible. (Le cahier évoque
  `MsgSendPulse` : ici le pulse de timer passe par le coid du dispatch —
  équivalent noyau, à instrumenter.)
- **E4 — CHANNEL disconnect** : `pulse_attach(_PULSE_CODE_DISCONNECT)` est
  enregistré (échec toléré à l'attach), et `veille_rm_peer_lost()` émet l'alarme
  technique ; la **livraison effective** du pulse de disconnect par procnto sur
  le canal du dispatch n'est pas prouvée tant que le resmgr n'a pas tourné.
- Le protocole `write("bpm N")` / `read()` → verdict texte n'a jamais été
  exercé par un vrai client `open("/dev/veille")`.
- `veille-sim` QNX n'a pas été exécuté (double preuve mesurée sur cible : à
  faire dans l'émulateur).

## 6. Différences d'API QNX 8.0 vs le squelette (vérifiées dans les en-têtes)

Le squelette initial supposait l'API SDP 7.x. Corrections apportées, toutes
vérifiées dans `target/qnx/usr/include/sys/` (et les symboles dans `libc.so`) :

| Squelette (7.x)                          | QNX 8.0 réel (dispatch.h/resmgr.h/iofunc.h) |
|------------------------------------------|----------------------------------------------|
| `resmgr_attach(...) → resmgr_connection_t*` (9 arg.) | `int resmgr_attach(dpp, attr, path, file_type, flags, connect_funcs, io_funcs, handle)` (8 arg., retour id `<0` = échec) ; plus de `resmgr_connection_t` |
| `resmgr_context_block(ctp)`              | `resmgr_block(ctp)` ; pour mixer resmgr + pulses : `dispatch_block/dispatch_handler` sur `dispatch_context_t` |
| `resmgr_handler(ctp, dispatch)`          | `resmgr_handler(ctp)` (1 arg.) / `dispatch_handler(ctp)` |
| `iofunc_attr_init(&attr, mode, NULL, NULL)` | existe toujours : `(attr, mode, dattr, client_info)` (macro vers `iofunc_attr_init_sized`) |
| pulse timer bricolé dans la boucle (`rcvid == 0`) | `message_connect(dpp, MSG_FLAG_SIDE_CHANNEL)` → coid pour `SIGEV_PULSE_INIT`, et `pulse_attach(dpp, MSG_FLAG_ALLOC_PULSE, code, func, handle)` qui route le pulse vers un handler dédié |
| devctl `RESMGR_NOREPLY` (sans underscore) | `_RESMGR_NOREPLY`, `_RESMGR_NPARTS(n)`, `_IO_SET_READ_NBYTES/_IO_SET_WRITE_NBYTES` (resmgr.h/iomsg.h) ; `iofunc_read_verify/iofunc_write_verify` prennent `io_read_t*/io_write_t*` |
| `CLOCK_MONOTONIC` via `_POSIX_C_SOURCE 199309L` | exige `__EXT_POSIX1_200112` : `_POSIX_C_SOURCE 200112L` (port) ou `_QNX_SOURCE` (resmgr) |

Le devctl `VEILLE_DEVCTL_PROOF` du squelette n'est **pas** repris : hors du
périmètre « minimal mais honnête » (read/write/tick/disconnect), et
`iofunc_devctl_default` renvoie proprement `ENOSYS`. La preuve exhaustive reste
accessible côté modèle (`make proof`) et embarquée dans `veille-sim`.

## 7. Pourquoi ce build n'est PAS dans la CI

- Les runners GitHub Actions n'ont **pas le SDP QNX 8.0** (licence + installation
  `~/qnx800` locale) ; `qcc` y est indisponible.
- La garde `.github/ci-budget/check_timeouts.py` impose ≤ 5 min par job : un job
  QNX nécessiterait d'installer/outiller un SDP complet, hors budget et hors
  périmètre des runners.
- La chaîne portable (`core/`, sim hôte, jumeau Python, différentiel, preuve)
  **est** couverte par la CI sur gcc ; `make qnx` est une cible **locale outillée**
  (poste avec SDP), documentée par la présente recette reproductible.

## 8. Usage prévu sur cible (quand l'émulateur sera prêt)

```sh
./veille-sim                    # démo chaîne capteur→alarme + double preuve (QNX)
./veille-rm &                   # resource manager /dev/veille (tick 10 ms auto)
echo "bpm 132" > /dev/veille    # pousse un échantillon horodaté côté serveur
cat /dev/veille                 # verdict courant au format texte du CONTRAT
```

