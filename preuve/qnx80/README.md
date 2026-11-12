# Preuves QNX 8.0 — journaux bruts

Chaque fichier est le **journal d'une exécution** : la commande jouée dans
l'invité, l'`uname` de l'hôte et de l'invité, la sortie brute et le code de
sortie. Rien n'y est réécrit après coup.

Les chiffres correspondants sont analysés et commentés dans
[`docs/QNX-EVIDENCE.md`](../../docs/QNX-EVIDENCE.md) (§5 et §6).
Pour rejouer la campagne : `bash tools/qnx/run-bench.sh all`
(voir [`tools/qnx/README.md`](../../tools/qnx/README.md)).

## Contenu de cette campagne (lot « preuves QNX manquantes »)

| Fichier | Essai | Ce qu'il contient |
|---|---|---|
| `e3-tick-repos-*.log` | E3 | cadence du tick au repos : ticks servis, intervalle min/max/moyen, écart max à la période en µs et en ppm, latence tick→verdict |
| `e3-tick-charge-*.log` | E3 | idem, avec un client qui inonde le rm pendant 20 s |
| `e3-sonde-independante-*.log` | E3 | **contrôle** : même timer 10 ms sur un canal dédié, sans rm (perte de pulses noyau ou traitement du rm ?) |
| `e4-capteur-muet-*.log` | E4 | verdict après 3 s de silence : alarme technique « capteur muet » |
| `e4-retour-signal-*.log` | E4 | un client se tait puis écrit : le verdict passe de « capteur muet » à « signal revenu » |
| `e4-stats-*.log` | E4 | compteurs du rm (watchdog, clients, disconnects) |
| `h2-repos-*.log` | H2 | 1000 allers-retours d'écriture au repos (µs, un échantillon par ligne) + statistiques du rm |
| `h2-charge-*.log` | H2 | idem sous charge |
| `e2-*-sature-*.log` | E2 | régime **saturé** : rm en file d'attente, hog SCHED_FIFO 30 + client inondeur |
| `e2-*-repos-*.log` | E2 | régime **au repos** : rm inactif, hog SCHED_FIFO 30 seul |
| `e2-*-stats-*.log` | E2 | priorités effectives vues par le rm (histogramme), base, état d'annulation du boost |

## Journaux des campagnes précédentes

Les journaux des campagnes antérieures (double preuve sur cible, resource
manager, rejeu de données PhysioNet réelles) sont dans l'archive **locale**
`~/tmp/qnx-evidence/` (non versionnée : ce sont des sorties de VM, pas des
sources). Ils sont décrits en §3 de `docs/QNX-EVIDENCE.md`. Les fichiers de ce
dossier sont ceux produits par la campagne **E2/E3/E4 + latences**, qui est
versionnée pour être rejouable et auditable.

## Lecture rapide

```bash
# les chiffres des latences et de la cadence
python3 tools/qnx/analyse.py preuve/qnx80

# les compteurs bruts d'un essai
grep -E '^(ticks|uptime_us|tick_maxdev_us|tick_maxdev_ppm|prio_hist)=' preuve/qnx80/e3-tick-repos-*.log
```

## Avertissement

Ces mesures ont été prises sur une **cible virtualisée** (QEMU/KVM) pendant que
d'autres machines virtuelles tournaient sur le même poste : la cadence du timer
et les queues de latence varient fortement d'une exécution à l'autre
(82–98 Hz observés pour le tick). Les journaux bruts sont là pour que le jury
puisse juger de la variabilité, pas seulement du chiffre final.
