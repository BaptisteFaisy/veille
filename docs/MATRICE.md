# Matrice exigence → test → preuve

> Générée automatiquement par `tools/matrice.py` depuis les sources du dépôt : toute ligne « non couverte » est un trou assumé, pas une erreur de génération. Régénérer : `python3 tools/matrice.py`.

| ID | Niveau | Exigence | Couverture (fichiers qui la citent) |
|---|---|---|---|
| S1 | S | Chaîne `sample→acquire→filter→decide→alarm→ack` avec timestamps fournis par l'appelant, en C11 pur (`core/`) | core/include/veille/chain.h, core/src/chain.c, target/pipe/veille_pipe.c |
| S2 | S | Jumeau Python stdlib (`host/`) : même contrat de sortie, implémentation séparée | host/veille/chain.py, host/veille/state.py, host/veille/verdict.py |
| S3 | S | Test différentiel C↔Python sur corpus de scénarios : tout désaccord est un bug | host/tests/test_proof.py, tests/differential.py |
| S4 | S | Exploration exhaustive d'un sous-ensemble d'états (capteur × bus, 2 priorités) avec preuve de borne | core/src/proof.c, core/tests/test_proof.c, host/tests/test_proof.py |
| S5 | S | Verdicts (10 codes) et rapports texte/JSON/Markdown avec empreinte SHA-256 | core/src/report.c, core/src/verdict.c |
| S6 | S | Fault injection : capteur bloqué/mort/bruité, bus saturé | scenarios/signal_dead.json, scenarios/signal_flat_60.json, target/pipe/veille_pipe.c |
| S7 | S | `make test` vert sans QNX, sans QEMU, sans licence | .github/workflows/ci.yml, Makefile |
| S8 | S | CI GitHub Actions : build C (`-Wall -Wextra -Werror`), tests Python, différentiel, garde taille fichiers | .github/workflows/ci-budget.yml, .github/workflows/ci.yml |
| C1 | C | Resource manager `/dev/veille` exposant la chaîne d'alarme (API typée par message passing) | docs/QNX-EVIDENCE.md, preuve/video/scenes.tsv, target/rm/resmgr_veille.c, target/rm/rm_io.c |
| C2 | C | Acquisition périodique par pulses/timers noyau (pas de `sleep()`) | **non couverte** |
| C3 | C | Priority inheritance `MsgSend` sur la voie critique : démontrée par kernel trace | **non couverte** |
| C4 | C | Exploration exhaustive complète (tous les états : capteur × bus × priorité × alarme × étage) — **✅ fait : 4800 états, < 10 ms** | core/src/proof.c, docs/QNX-EVIDENCE.md, tests/differential.py |
| C5 | C | Kernel trace (`tracelogger`) capturé et converti en preuve empirique de latence | **non couverte** |
| C6 | C | Fault injection sur cible : panne d'étage, `CHANNEL` disconnect notifié aux pairs | **non couverte** |
| C7 | C | Image QNX (`mkifs`) bootable sur QEMU pour la démo | **non couverte** |
| C8 | C | Codelab 4 chapitres : « prouver la latence d'une alarme médicale sur QNX » | **non couverte** |
| C9 | C | Adaptive partitioning : partition critique (alarme) vs best-effort (UI), démontrée sous charge | **non couverte** |
| X1 | X | Preuve formelle assistée (coq/why3) de la borne sur le modèle d'états | **non couverte** |
| X2 | X | Intégration capteurs réels (ECG/SpO2 matériel) avec isolation galvanique | **non couverte** |
| X3 | X | Dossier IEC 62304 complet (traçabilité exigences→tests→preuves) | **non couverte** |
| X4 | X | Redondance failover de la chaîne d'alarme (deux calculateurs, comme Relais) | core/tests/test_proof.bin |

**Bilan** : 21 exigences — 11 citées par au moins un test ou une preuve, 10 non couvertes.
