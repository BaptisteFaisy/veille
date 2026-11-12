# Veille — preuve sur cible QNX 8.0

Ce document est le **compte rendu factuel** de ce qui a été exécuté sur une vraie
cible QNX 8.0 (émulateur QEMU), et de ce qui ne l'a pas été. Les journaux bruts
sont dans [`preuve/qnx80/`](../preuve/qnx80/) — un fichier par exécution, avec la
commande, l'`uname` de l'hôte et de l'invité, la sortie et le code de sortie.

Date : 12 novembre 2026. Auteur : b (agent).

---

## 1. Environnement de la cible

| Élément | Valeur |
|---|---|
| Système invité | `QNX qnxqemu 8.0.0 2026/06/05-16:26:03EDT x86pc x86_64` |
| Image | QNX Everywhere Quick Start Target Image (QEMU), `qnx_sdp8.0_qemu_quickstart_20260902` |
| Émulation | QEMU 8.2.2, KVM activé, 3 Gio de RAM, 4 vCPU |
| Compilateur | SDP 8.0 (QNX Software Center), `qcc` = GCC **12.2.0**, cible `gcc_ntox86_64` |
| Accès | SSH root par clé (`PermitRootLogin prohibit-password` modifié dans l'image), console série TCP |
| Chaîne porteuse | `core/` (C11 pur) + `host/` (jumeau Python) + `target/` (resmgr, sim, pipe) |

Recette de mise en route (hôte Linux) :

```bash
# 1. Dépaquetage SÉLECTIF de l'image quickstart (le disque fait 48 Go ;
#    seul le disque brut est inutile : ifs.bin + build/ suffisent)
cd ~/qnx800/images/qemu
cat qnx_sdp8.0_qemu_quickstart_20260902.tar.gz.* | tar -xzf - qemu/output/ifs.bin qemu/output/build
# 2. Boot (le disque pré-construit de 48 Go reste sparse : ~4,9 Go réels)
cd qemu
qemu-system-x86_64 -smp 4 --enable-kvm --cpu host -m 3G \
  -drive file=output/disk-qemu.vmdk,if=ide,id=drv0 -kernel output/ifs.bin \
  -display none -vga none \
  -chardev socket,id=ser0,host=127.0.0.1,port=4444,server=on,wait=off -serial chardev:ser0 \
  -netdev user,id=net0,hostfwd=tcp:127.0.0.1:8022-:22 -device virtio-net-pci,netdev=net0
# 3. Identifiants de l'image (doc officielle QNX Everywhere) : root / root
```

## 2. Compilation croisée (`make qnx`)

`make qnx` compile `core/` + `target/` avec le **vrai qcc** du SDP 8.0 :

```
build/qnx/veille-sim: ELF 64-bit LSB pie executable, x86-64, dynamically linked,
                       interpreter /usr/lib/ldqnx-64.so.2
build/qnx/veille-rm:  ELF 64-bit LSB pie executable, x86-64, dynamically linked,
                       interpreter /usr/lib/ldqnx-64.so.2
```

Écarts assumés (détaillés dans [`QNX-BUILD.md`](QNX-BUILD.md)) : pas de `-D__QNX__`
(qcc le pré-définit à `800`, un `-D__QNX__` nu casse `-Werror`), `-D_QNX_SOURCE`
pour `timer_create`/`CLOCK_MONOTONIC` et les extensions QNX (pulses).

## 3. Exécutions réelles sur la cible

### 3.1 Démonstration C (`veille-sim`) — même bilan que sur l'hôte

```
alarmes physiologiques : 291 (latence max 0.001 ms, borne prouvée 200 ms)
alarmes techniques     : 8 (latence max 0.000 ms, borne 50 ms)
marge de sûreté        : 200 ms (borne prouvée - latence mesurée max)
[OK] L_measured <= B_proof sur tous les échantillons — double preuve cohérente.
```

Identique à la sortie hôte : la chaîne C se comporte de même sous QNX 8.0.
Journal : `preuve/qnx80/preuve-cible-synth-*.log`.

### 3.2 Exploration exhaustive des 4800 états — sur la cible

Le jumeau Python (Python **3.14** dans l'image) parcourt les 4800 états de
défaillance **sur QNX** :

```
ERROR  VEILLE_PROOF_COUNTEREXAMPLE  bound=100ms  latency=105ms  states=4800
FAILED 1 error(s)
real 0m0.126s
```

Même verdict et même temps que sur l'hôte (`(4800, 105)`), en deux ordres de
grandeur de temps Machine.

### 3.3 Resource manager `/dev/veille` — les quatre issues de la chaîne

Écritures réelles dans le nœud, lectures du verdict au format texte du contrat :

| Cas | Écriture | Verdict sur cible |
|---|---|---|
| Rythme normal | 8 échantillons ~72 bpm | `INFO VEILLE_OK … alarm_none bound=200` |
| Tachycardie soutenue | 8 échantillons à 132 bpm | `INFO VEILLE_OK … alarm_single bound=200` (alarme haute déclenchée) |
| Capteur figé | même valeur répétée | `WARN VEILLE_TECHNICAL_ALARM … sensor_stuck … bound=50` |
| Capteur mort | valeur négative | `WARN VEILLE_TECHNICAL_ALARM … sensor_dead … bound=50` |
| Retour normal | 8 échantillons ~72 bpm | `INFO VEILLE_OK … alarm_none bound=200` |

Journal : `preuve/qnx80/preuve-resmgr-cible-*.log`.

### 3.4 Données réelles (PhysioNet) rejouées **dans** l'émulateur

| Jeu | Enregistrement | Signal | Résultat sur cible |
|---|---|---|---|
| MIT-BIH Arrhythmia | 100 | ECG MLII, 360 Hz | `INFO VEILLE_OK chain=100_MLII latency=50ms` (rythme sinusal normal : aucune alarme, conforme) |
| MIT-BIH Arrhythmia | 105 | ECG MLII | `INFO VEILLE_OK chain=105_MLII latency=50ms` |
| MIT-BIH Arrhythmia | 222 | ECG MLII (fibrillation atriale) | 2500 pics R détectés, 2401 échantillons de bpm réels écrits dans `/dev/veille` (bpm 43 → 182, moyenne 87,9) |
| MIT-BIH Arrhythmia | 205 | ECG MLII (tachycardie ventriculaire) | 2647 pics R, bpm 46 → 200 |
| BIDMC | bidmc01 | ECG + PLETH + SpO2 | SpO2 réel lu 96–98 %, HR 88–95 bpm |
| MIT-BIH Polysomnographic | slp02a | ECG + pression artérielle | PA réelle : 41 → 109,47 mmHg |

Le rapport d'audit produit **sur la cible** porte l'empreinte du fichier source :

```
- Configuration : /data/veille-data/mitdb/105
- Empreinte SHA-256 : fcd0153dfea69c749194bb73de7db124588857cfa2f6aecb72754894c8afde02
- Horodatage (UTC) : 2026-11-12T14:45:18Z
```

Journaux : `preuve/qnx80/preuve-replay-mitdb*-*.log`,
`preuve/qnx80/preuve-reel-*-*.log`, `preuve/qnx80/preuve-vt205-cible-*.log`.

## 4. Défauts trouvés en passant sur la vraie cible (corrigés)

1. **`io_write` retournait le nombre d'octets comme code d'erreur.** Le handler
   terminait par `return _IO_SET_WRITE_NBYTES(ctp, nb);` — cette macro *pose* le
   statut dans `ctp` et **retourne sa valeur** (le nombre d'octets). Le client
   recevait donc `EINVAL`-like : `E2BIG` pour 7 octets, `ENOEXEC` pour 8, `ENXIO`
   pour 6 — c'est-à-dire un errno déduit de la taille de l'écriture. Le pattern
   officiel du SDP (`s1_resmgr_write_simple`) impose `_IO_SET_WRITE_NBYTES(ctp, n)`
   puis `return EOK`.
2. **Lecture des données par copie contiguë.** `memcpy(buf, (const char *)(msg+1), nb)`
   suppose les données collées à l'en-tête `io_write_t` ; le SDP impose
   `resmgr_msgget(ctp, buf, nb, sizeof(msg->i))`.
3. **Une seule valeur par écriture.** Un client qui écrit en tampon (Python :
   buffer de 8 Ko) envoie plusieurs lignes d'un coup → `EINVAL`. Le serveur
   accepte désormais jusqu'à 256 échantillons par écriture (une ligne invalide
   rejette l'écriture entière : aucune moitié n'est poussée).
4. **`O_CREAT` sur un périphérique.** `os.open('/dev/veille', O_WRONLY|O_CREAT)`
   renvoie `EINVAL` : le resource manager refuse la création. Le client ouvre
   désormais en écriture seule si le chemin existe, et en mode ligne par ligne
   (un échantillon par `write()`), ce qui préserve la cadence réelle.
5. **Notification de disconnect parasite.** La notification `_PULSE_CODE_DISCONNECT`
   arrivait sans client connecté et empoisonnait le verdict courant. Le serveur
   compte désormais les clients (handler `open`) et n'alerte que si un client
   était réellement connecté.

## 5. Essais du cahier des charges : état réel

| Essai | Question | État | Preuve |
|---|---|---|---|
| E1 | Bornes et priorités IEC 60601-1-8 | **partiel** | Ordres de grandeur publics documentés dans `CONTRACT.md` ; la norme payante n'a pas été lue |
| E2 | Priority inheritance `MsgSend` observable par kernel trace | **non démontré** | Trace capturée sur cible (3,4 Mo, en-tête `TRACE_VER_MAJOR::2`, QNX 8.0.0) mais l'outil `traceprinter` du SDP installé (version 1.02, janvier 2025) la refuse : *TRACEPARSER: function call traceparser() failed, internal error code(12)* — le format de trace de l'image (septembre 2026) a évolué depuis le SDP installé. Analyse `sched`/`msg`/`timer` à refaire avec un SDP de même version |
| E3 | Cadence `timer_create` + `MsgSendPulse` stable sous charge | **non mesuré** | Le tick noyau existe (`VEILLE_PERIOD_MS = 10`, `SIGEV_PULSE_INIT` sur un coid de canal latéral) et la chaîne simule un capteur à ce rythme, mais la dérive n'a pas été chiffrée sur cible |
| E4 | `CHANNEL` disconnect notifié aux pairs | **non démontré** | La notification `_PULSE_CODE_DISCONNECT` n'est pas reçue au niveau du dispatch pour un client iofunc : la mort d'un client ne déclenche pas d'alarme technique. Le mécanisme correct (attache par canal client) reste à implémenter |

Ces trois essais sont **explicitement non validés** : rien dans ce dépôt ne prétend
le contraire.

## 6. Limites de cette preuve

- **Émulateur, pas du matériel** : la cible est un x86_64 virtualisé (KVM). Aucune
  mesure ne vaut pour un vrai moniteur patient ni pour une cible QNX embarquée.
- **Signaux cliniques simulés à l'entrée du resource manager** : `/dev/veille`
  reçoit du bpm (déduit de l'ECG réel par le client). Le rejeu du signal brut
  (acquire → filter) n'est fait que par le jumeau Python.
- **Détection de pics R heuristique** (seuil adaptatif, non clinique) : les bpm
  extraits d'un ECG réel en fibrillation atriale oscillent fortement, et le
  « capteur figé » de la chaîne se déclenche dès que deux bpm consécutifs
  arrondis sont égaux — c'est un vrai enseignement des données réelles, à traiter
  au niveau du signal brut plutôt que du bpm.
- **Pas d'inversion de priorité mesurée**, pas de charge réelle (coeur/ESD/réseau).
- **Données PhysioNet** : accès libre, licence ODC-By v1.0, aucune donnée n'est
  committée dans ce dépôt ; voir [`REAL-DATA.md`](REAL-DATA.md).
