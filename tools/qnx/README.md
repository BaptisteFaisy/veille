# Veille — outillage de preuve QNX 8.0 (`tools/qnx/`)

Outillage **rejouable** de la campagne de mesures décrite dans
[`docs/QNX-EVIDENCE.md`](../../docs/QNX-EVIDENCE.md) (§5 et §6) : essais E2
(héritage de priorité), E3 (cadence du timer), E4 (silence du capteur) et
latences réelles sous charge.

Tout ce qui suit se lance depuis la **racine du dépôt**.

---

## 1. Prérequis

| Besoin | Détail | Où le vérifier |
|---|---|---|
| SDK QNX 8.0 | `qcc` (GCC 12.2.0), cible `gcc_ntox86_64` | `~/qnx800/qnxsdp-env.sh` (variable `QNX_SDP`) |
| Image QNX | QNX Everywhere **Quick Start Target Image** (QEMU) | `~/qnx800/images/qemu/qemu/output/ifs.bin` |
| KVM | virtualisation accélérée disponible | `ls /dev/kvm` |
| Python 3 | ≥ 3.8 (analyse des journaux) | `python3 -V` |
| Accès SSH à l'invité | clé `~/.ssh/qnx-vm_ed25519`, `root@127.0.0.1` | `ssh -p 8022 -i ~/.ssh/qnx-vm_ed25519 root@127.0.0.1` |

Ports utilisés (tous en `127.0.0.1`) :

| Port | Rôle | Configurable |
|---|---|---|
| **8022** | SSH de l'invité QNX (redirection de port QEMU) | `SSH_PORT` |
| **4444** | console série QNX (socket TCP) | `SERIAL_PORT` |

Identifiants : **root**, sans mot de passe (authentification par clé SSH).
La console série demande `root` / `root` (identifiants de l'image Quick Start).

## 2. Démarrer / arrêter la VM

```bash
bash tools/qnx/boot.sh --start     # démarre QEMU et attend le SSH (jusqu'à ~2 min)
bash tools/qnx/boot.sh --status    # « VM vivante (pid …) » + « SSH joignable »
bash tools/qnx/boot.sh --stop      # arrêt propre : SIGTERM puis SIGKILL du PID
```

Le script n'arrête **que** la VM qu'il a lancée (PID file
`output/qemu.pid`) : les autres machines virtuelles de la machine ne sont pas
touchées. Variables : `QNX_VM_DIR`, `SSH_PORT`, `SERIAL_PORT`, `MEM`, `CPUS`.

## 3. Compiler (croisé) et pousser dans l'invité

```bash
bash tools/qnx/build.sh            # → build/qnx/{veille-rm,bench_client,hog,tick_probe}
```

Le build utilise le `qcc` du SDP 8.0 (`. $QNX_SDP/qnxsdp-env.sh`). Pour une
cible aarch64 : `QCC_V=gcc_ntoaarch64le bash tools/qnx/build.sh`.

Pour pousser les binaires dans l'invité, deux moyens :

* **via le partage HTTP** (le plus simple) : les fichiers sont déposés dans
  `/tmp/qnx-share` côté hôte, un petit serveur HTTP les sert sur le port 8123,
  et l'invité les récupère sur `10.0.2.2:8123` :

  ```bash
  cp build/qnx/veille-rm build/qnx/bench_client build/qnx/hog build/qnx/tick_probe /tmp/qnx-share/
  /tmp/qnx-ssh 'mkdir -p /data/w5 && cd /data/w5 && for n in veille-rm bench_client hog tick_probe; \
      do curl -sf -o $n.new http://10.0.2.2:8123/$n && mv -f $n.new $n && chmod +x $n; done; ls -l'
  ```

  (on écrit dans un `.new` puis `mv` : impossible d'écraser un binaire en
  cours d'exécution, `ETXTBSY` ; le `mv` remplace l'entrée de répertoire) ;

* ou `~/tmp/qnx-veille-tools/push <fichiers…>` si cet outil est présent.

## 4. Lancer la campagne de mesures

```bash
bash tools/qnx/run-bench.sh        # tout : e3, e4, h2, e2
bash tools/qnx/run-bench.sh e3     # un seul essai (e2 | e3 | e4 | h2)
python3 tools/qnx/analyse.py preuve/qnx80    # tableaux de chiffres (p50/p95/p99…)
```

Durée : ~6 min pour la campagne complète. Chaque mesure produit **un journal**
dans `preuve/qnx80/` (`<essai>-<AAAAMMJJTHHMMSSZ>.log`) contenant la commande,
l'`uname` de l'hôte et de l'invité, la sortie brute et le code de sortie.

Variables : `OUT` (dossier des journaux, défaut `preuve/qnx80`), `DEST`
(dossier des binaires dans l'invité, défaut `/data/w5`), `SSH_PORT`, `CLE`.

### Ce que font les quatre essais

| Essai | Ce qui est mesuré | Journaux |
|---|---|---|
| `e3` | cadence du tick (10 ms) au repos puis sous charge, + **sonde indépendante** sur canal dédié | `e3-tick-repos-*`, `e3-tick-charge-*`, `e3-sonde-independante-*` |
| `e4` | watchdog « capteur muet » : alarme levée, puis levée quand le signal revient | `e4-capteur-muet-*`, `e4-retour-signal-*`, `e4-stats-*` |
| `h2` | latence échantillon→verdict (aller-retour client) au repos puis sous charge | `h2-repos-*`, `h2-charge-*` |
| `e2` | héritage de priorité : 7 configurations (rm saturé / au repos × héritage / sans / production) | `e2-*` et `e2-*-stats-*` |

### Les outils de mesure (C, compilés pour QNX)

| Binaire | Rôle |
|---|---|
| `bench_client` | client de mesure : `stats`, `verdict`, `hold`, `samples --n --prio --interval-us --bpm --stats` |
| `hog` | occupation CPU à priorité SCHED_FIFO donnée (`--prio --hold-ms --sleep-ms --duration-ms`) |
| `tick_probe` | sonde de cadence : même timer 10 ms sur son **propre canal**, sans rm |

`bench_client stats` lit le **canal de mesures** du rm : un `read()` à l'offset
réservé `VEILLE_STATS_OFFSET` (`0x40000000`) qui rend un texte `cle=valeur`
(ticks, intervalles, écarts en ppm, priorités observées, latences, watchdog).
Ce canal est **hors du format du CONTRAT**, qui n'est pas modifié.

## 5. Tout arrêter

```bash
bash tools/qnx/boot.sh --stop                     # la VM
/tmp/qnx-ssh 'slay -9 veille-rm; slay -9 bench_client; slay -9 hog'   # l'invité
```

Dans l'invité, `pidin -F '%p %n'` liste les processus (**les PID sont en
hexadécimal**) ; `slay -9 <nom>` tue par nom. Les processus lancés en
arrière-plan par le banc (`hog`, `bench_client`) se terminent seuls à la fin
de chaque mesure (`kill $PID` explicite dans le script).

## 6. Pièges rencontrés (à connaître avant de rejouer)

1. **`MSG_FLAG_ALLOC_PULSE` casse la liaison timer ↔ handler.** Avec ce
   drapeau, `pulse_attach` **ignore** le code demandé et en alloue un autre ;
   le timer envoie pourtant toujours au code écrit dans `SIGEV_PULSE_INIT` →
   le tick n'est jamais servi. Utiliser `pulse_attach(dpp, 0, code, …)`.
2. **Le canal latéral n'est pas servi par `dispatch_block()`.** Le coid du
   timer doit venir de `message_connect(dpp, 0)` (canal principal), pas de
   `message_connect(dpp, MSG_FLAG_SIDE_CHANNEL)`.
3. **Un processus lancé en arrière-plan garde le canal SSH ouvert** : le
   `sshd` de l'invité attend la fin de session, donc la commande d'hôte ne
   revient qu'à la mort du processus. Le banc lance donc **tous** les acteurs
   d'une mesure dans **une seule** commande invité, avec les PID capturés.
4. **`struct itimerspec` est en nanosecondes** : `it_value.tv_nsec = 10 ms`
   s'écrit `10000000`, pas `10000` (sinon le timer tourne 1000× trop vite —
   c'est ainsi qu'un premier « tick à 316 Hz » a été observé, et corrigé).
5. **Le verdict se relit depuis l'offset 0** : après un `read()`, l'offset de
   l'OCB est en fin de rapport ; un `lseek(fd, 0, SEEK_SET)` est nécessaire
   pour relire le verdict courant.
