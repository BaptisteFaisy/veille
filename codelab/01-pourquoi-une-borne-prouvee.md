# Chapitre 1 — Pourquoi une borne **prouvée**, pas mesurée

## 1.1 L'alarme médicale est un chemin critique à deadline

Un moniteur patient surveille des signaux physiologiques (ECG, SpO₂, pression artérielle) et doit **alerter l'opérateur** quand un seuil est franchi. La chaîne est :

```
échantillon capteur → acquisition → filtrage → décision → alarme audible
```

Le temps qui s'écoule entre l'échantillon (`t0`) et le déclenchement de l'alarme (`t4`) est la **latence de bout en bout** :

```
L = t4 − t0
```

Si `L` dépasse une borne, l'opérateur est prévenu trop tard. Sur un patient en détresse, quelques centaines de millisecondes font la différence. **L'alarme n'est pas une fonctionnalité parmi d'autres : c'est un chemin critique avec une deadline.**

C'est exactement le même raisonnement que pour une boîte noire automobile qui doit rendre le crash durable en 20 ms (projet **Ambre**), ou un steer-by-wire qui doit transférer le contrôle sans gap (projet **Relais**). La différence : ici, la deadline protège un patient, et la norme qui l'exige est **IEC 60601-1-8**.

## 1.2 Ce qu'exige IEC 60601-1-8 (et pourquoi c'est dur)

La norme IEC 60601-1-8 spécifie les **systèmes d'alarme** des équipements électromédicaux :

- trois **priorités** d'alarme physiologique (haute, moyenne, basse), chacune avec des caractéristiques temporelles et un **profil sonore distinct** ;
- des **alarmes techniques** (défaillance du dispositif lui-même : capteur déconnecté, panne) ;
- l'**acquittement** et le **verrouillage** des alarmes.

> ⚠️ Les **valeurs exactes** des délais sont dans la norme payante. Ce codelab utilise des ordres de grandeur **configurables** (haute ≈ 100–200 ms, technique ≈ 50 ms). Voir `docs/IEC60601-8.md` et l'essai E1 du cahier des charges. La méthode, elle, ne dépend pas des valeurs.

Et IEC 62304 (logiciel de dispositif médical) exige de **prouver** que ces délais sont tenus — pas seulement de les mesurer une fois.

## 1.3 Mesurer n'est pas prouver

L'approche classique : on branche un oscilloscope ou un profileur, on déclenche une alarme, on mesure `L`, on note « 12 ms, ça passe ».

**Le problème :** cette mesure ne vaut que pour le scénario testé. Elle ne dit rien des cas où :

- le capteur envoie une valeur **figée** (panne silencieuse) ;
- le capteur est **mort** (plus d'échantillon du tout) ;
- le bus est **saturé** par un autre équipement ;
- une tâche de **moindre priorité tient un verrou** dont la voie critique a besoin (inversion de priorité) ;
- **plusieurs alarmes** se déclenchent en même temps ;
- un **étage de la chaîne tombe**.

Chacun de ces états change la latence. Mesurer un seul scénario, c'est prouver un seul scénario. Or la combinaison de ces défaillances est **finie et énumérable** : c'est exactement ce qu'on peut explorer **exhaustivement**.

## 1.4 Pourquoi QNX 8.0 est la bonne base

Prouver une borne sur un OS généraliste est impossible : le scheduler ne garantit pas de délai, l'inversion de priorité n'est pas corrigée, la mort d'un processus n'est pas notifiée de façon déterministe. QNX 8.0 (RTOS microkernel, gratuit en non-commercial via *QNX Everywhere*) donne les mécanismes qui rendent la borne **atteignable et vérifiable** :

| Mécanisme QNX | Ce qu'il garantit à la chaîne d'alarme |
|---|---|
| **Priority inheritance** à travers `MsgSend` | Quand la voie critique (priorité 62) envoie un message au sink d'alarme, le noyau fait tourner le sink à la priorité 62 le temps du message. Une tâche best-effort ne peut **pas** préempter la voie critique. L'inversion de priorité est **corrigée par le noyau**, pas seulement détectée. |
| **Pulses et timers noyau** (`timer_create`, `MsgSendPulse`) | La cadence d'acquisition est périodique et stable, sans `sleep()` sujet à la dérive du scheduler. |
| **Resource managers** (`resmgr_*`) | `/dev/veille` : un seul processus possède la chaîne ; les clients y accèdent par API typée. Pas de fichier partagé, pas de verrou à dimensionner à la main. |
| **Microkernel + `CHANNEL` disconnect** | Quand un étage meurt, le noyau **notifie** ses correspondants. La décision sait que l'acquisition est tombée et déclenche une **alarme technique** au lieu d'attendre en silence. |
| **Adaptive partitioning** | La partition critique (alarme) est isolée de la partition best-effort (UI, réseau) : la charge de l'UI ne peut pas retarder l'alarme. |
| **Kernel trace** (`tracelogger`) | Capture horodatée des `MsgSend`, timers et changements de priorité : la latence **mesurée** sur le système réel devient une preuve empirique. |

## 1.5 L'approche Veille : la double preuve

Veille combine deux preuves complémentaires :

1. **Preuve exhaustive (modèle).** On énumère **tous** les états de défaillance atteignables de la chaîne (4800 états), et pour chacun on vérifie que la latence pire-cas reste dans la borne, ou qu'une alarme technique se déclenche dans sa propre borne. Résultat : `VEILLE_PROOF_COMPLETE` (borne tenue partout) ou `VEILLE_PROOF_COUNTEREXAMPLE` (contre-exemple rejouable).

2. **Preuve empirique (cible).** Sur QNX (QEMU ou Raspberry Pi 5), le kernel trace mesure la latence réelle `L_measured`. On vérifie `L_measured ≤ B_proof` : la borne prouvée couvre le réel. L'écart est la **marge de sûreté**.

```
modèle (4800 états)  ──prouve──►  B_proof
                                      │
cible QNX (kernel trace) ──mesure──► L_measured  ≤  B_proof   ✓
```

C'est cette double preuve qui transforme « l'alarme a sonné » en « l'alarme **ne peut pas** être en retard, et voici le certificat ».

## 1.6 Ce que vous allez construire

Dans les chapitres suivants, vous allez :

- **Chapitre 2** : construire la chaîne en C11 pur (`core/`) et son jumeau Python indépendant (`host/`), et les faire vérifier l'un par l'autre (différentiel).
- **Chapitre 3** : lancer l'exploration exhaustive des 4800 états, lire un contre-exemple, et générer le rapport d'audit IEC 62304.
- **Chapitre 4** : porter la chaîne sur QNX 8.0 (resource manager, pulses/timers, priority inheritance, kernel trace).

Tout le socle (chapitres 2 et 3) tourne **sans QNX**. Le chapitre 4 est le guide vers la cible réelle.

→ [Chapitre 2 : Construire la chaîne](02-construire-la-chaine.md)
