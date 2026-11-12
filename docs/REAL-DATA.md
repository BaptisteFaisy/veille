# Données réelles — Veille (provenance et honnêteté)

Ce document dit **ce qui a été réellement mesuré**, **par qui**, **sous quelle
licence**, et **ce qui reste hors périmètre**. Aucun chiffre de ce document
n'est inventé : tout vient d'un fichier réellement présent dans
`data/records/` (non versionné) et vérifié par empreinte SHA-256 contre le
`SHA256SUMS.txt` publié par PhysioNet.

Les cinq livrables de ce lot :

| Fichier | Rôle |
|---|---|
| `host/veille/wfdb.py` | lecteur WFDB (formats 212 et 16) + CSV numériques BIDMC |
| `host/veille/replay.py` | rejeu d'un signal réel dans la chaîne existante (`chain.py`, `state.py`, `verdict.py`, `report.py`) |
| `host/veille/resmgr_client.py` | pics R + bpm instantané → lignes `bpm <n>` vers `/dev/veille` |
| `host/tests/test_replay.py` | tests déterministes sur les données réelles présentes |
| `data/fetch.py` | téléchargement vérifié (déjà écrit, committé tel quel) |

---

## 1. Les trois jeux de données

| Jeu | Ce qui est mesuré | Patients | Cadence | Format | Durée |
|---|---|---|---|---|---|
| **MIT-BIH Arrhythmia** (`mitdb`, v1.0.0) | ECG 2 dérivations (MLII, V5) | **48** | 360 Hz | 212 (12 bits) | 30 min / enregistrement |
| **MIMIC-II Waveform — sous-ensemble *matched*** (`bidmc`, v1.0.0) | RESP, PLETH, V, AVR, **II (ECG)** + CSV SpO2/HR | **53** (réanimation, MICU) | 125 Hz | 16 (int16) | 8 min / enregistrement |
| **Sleep-EDF Expanded** (`slpdb`, v1.0.0) | ECG, **BP** (mmHg), EEG, Resp nasale | 20 adultes (§2) | 250 Hz | 212 (12 bits) | ~8–10 h / nuit |

Fichiers effectivement retenus (petit lot, déterministe, ≤ 100 Mo) :

- `mitdb/100` — rythme sinusal normal ; `mitdb/105` — extrasystoles
  ventriculaires, « high-grade noise and artifact ».
- `bidmc/bidmc01` (patient **88 ans**, homme, MICU, segment `s01182`,
  2688-03-25 23:14) et `bidmc/bidmc02` (patient **65 ans**, homme, MICU,
  segment `s01241`), plus les CSV `bidmc_01/02_{Numerics,Breaths}.csv`.
- `slpdb/slp01a` (44 ans, homme, 19/01/1989) et `slpdb/slp02a` (38 ans,
  homme, 01/02/1989).

### 1.1 Les trois jeux ne viennent pas du même patient

C'est le point le plus important de ce document :

- **MIT-BIH** : ECG seul (2 dérivations). Aucune SpO2, aucune PA.
- **BIDMC** : ECG (II) **et** SpO2/HR/RESP dans le CSV numérique **du même
  patient et du même séjour de réanimation** — c'est le seul couple
  « ECG + SpO2 » réellement synchronisé dont nous disposons.
- **Sleep-EDF** : ECG **et** pression artérielle (BP), **mais pas de SpO2**.

On ne peut donc **pas** affirmer « ECG + SpO2 + pression artérielle du même
patient » : ce triplet n'existe pas dans les données téléchargées.

### 1.2 Les fichiers BIDMC ne sont pas des octets bruts du moniteur

Les en-têtes BIDMC portent la mention de PhysioNet :

> `this is not a verbatim copy of an original file. Please see the accompanying
> LICENSE.txt file for further details.`

Le sous-ensemble *matched* a été **reprocessé** (mise à l'échelle, choix des
segments) : les valeurs sont de vraies mesures de patients, mais pas les
octets d'origine du moniteur. À garder en tête pour toute publication.

### 1.3 Unités

`ECG`, `V`, `AVR` en mV ; `BP` en mmHg ; `PLETH` en NU (unités arbitraires du
pléthysmographe) ; `RESP` en pm (par minute) ; `SpO2`, `HR`, `PULSE` en
pourcentage et en bpm (CSV numérique, une ligne par seconde).

---

## 2. Licences

Tous les jeux utilisés sont publiés par **PhysioNet** sous l'
**Open Data Commons Attribution License v1.0** (ODC-By 1.0) :
<https://physionet.org/about/license/>.

L'attribution est **obligatoire** : toute réutilisation doit citer PhysioNet
et l'article de référence (Goldberger 2000, ci-dessous) ainsi que le jeu
concerné. Les fichiers `.atr` sont distribués sous la même licence que le
jeu dont ils sont issus.

---

## 3. Citations exigées

1. **PhysioNet (obligatoire pour tous les jeux)** — Goldberger AL, Amaral
   LAN, Glass L, Hausdorff JM, Ivanov PC, Mark RG, Mietus JE, Moody GB,
   Peng C-Y, Stanley HE. *PhysioBank, PhysioToolkit, and PhysioNet:
   components of a new research resource for complex physiologic signals.*
   Circulation. 2000;101(23):e215–e220. doi:10.1161/01.CIR.101.23.e215
2. **MIT-BIH** — MIT-BIH Arrhythmia Database [Data set]. PhysioNet.
   <https://physionet.org/content/mitdb/1.0.0> (1999).
3. **BIDMC / MIMIC-II** — Moody GB, Mark RG. *The MIMIC-II database: 3,000
   adult and pediatric patients, 5,000 waveforms, 10,000 spreadsheets.* 2011
   Annual International Conference of the IEEE Engineering in Medicine and
   Biology Society (EMBC). IEEE, 2011, pp. 2482–2484.
   doi:10.1109/EMBC.2011.6221023
4. **Sous-ensemble *matched*** — MIMIC-II Waveform Database Matched Subset
   [Data set]. PhysioNet. <https://physionet.org/content/mimic2wdb/1.0.0>
   (2012).
5. **Sleep-EDF** — Kemp B, Holmes AL, Zschech C, Rosenhahn R. *Sleep EDF:
   Expanded PhysioBank Database* (version 1.0.0) [Data set]. PhysioNet.
   <https://physionet.org/content/sleep-edf/1.0.0> (2018).

---

## 4. Empreintes SHA-256 (vérifiées)

Les 18 fichiers présents ont été recalculés localement et **conformes** aux
`SHA256SUMS.txt` publiés par PhysioNet (18/18) :

```
b2ea3c250e56e48f4b7b90697832b8ecd1afa1e0bb31f2dcfea4ed6e1075a639  mitdb/100.dat
60ebc904c7bf3e04d142638d3fd5c903e8dc9f10f1ea3264e07926aa089ee75e  mitdb/100.hea
8d8a5349fb16638ebbf649f1779d12e96d91b736b2aafe59db43719ae583d471  mitdb/100.atr
fcd0153dfea69c749194bb73de7db124588857cfa2f6aecb72754894c8afde02  mitdb/105.dat
9a024eebf8e9baf630308815e689d7e3eab471ab0069db6aded127c396418d48  mitdb/105.hea
278d534c1ad952a6d41db963b6b2b00be070d8dd5fa66545caa5c18edcc36497  mitdb/105.atr
b1666c7f2f117be6dc04cae2e7016b3315775edb9ad7c7ee53fa9c110937560b  bidmc/bidmc01.dat
f43b0b139ad8f4d45097403b7179e1e6f8bda17dfd06dba504faf39a115aa27f  bidmc/bidmc01.hea
6437e4eb11a05eb5a0e65eb0a3a5d8f6e5dbe719e75d4264e86d27ba65870bf4  bidmc/bidmc02.dat
b354f10cabfde4ffc91d4560c7bad54fc466f4319d55bee0f1b7073e9211bfab  bidmc/bidmc02.hea
27d43794cf2e7150db10e8bfe61d2bfdb26873a8f1629ffc5fbee5c9a4eb6ef5  bidmc/bidmc_csv/bidmc_01_Numerics.csv
99aef20b2846815d45ecde184da753de58c8a85b7dd7af74a2f4c5282013704d  bidmc/bidmc_csv/bidmc_02_Numerics.csv
698846517e27e7789d855875bae9774db3c189900efae8e486c300ed5ce58037  bidmc/bidmc_csv/bidmc_01_Breaths.csv
b17230d3a2b3f7063b3a2e9b4dc94e46bf02c1dc7b3f71ee0507e0598d6609ac  bidmc/bidmc_csv/bidmc_02_Breaths.csv
3be9ecc08cef24b714374e51324b5b53ef05d8b4ab1dfc25b007b38d0bcbd00b  slpdb/slp02a.dat
7f7254130285b52c602f5b80f682a15a9d939faf666778f8165054db37f40570  slpdb/slp02a.hea
80f04f98de84c6e342ffda59b597c70d956501f1a827cf2fea04d112c8cd7257  slpdb/slp01a.dat
05bfae85818ffd2fd9586daad74c17ec47cc94d47794c11fb9d3e451a9d7c0da  slpdb/slp01a.hea
```

Le contrôle d'intégrité du décodage ne repose pas sur ces empreintes seules :
le champ `checksum` de chaque en-tête WFDB (somme 16 bits signée de tous les
échantillons du signal) est **recalculé** par `veille.wfdb.somme_16_signee` et
comparé à la valeur publiée :

| Signal | recalculé | en-tête |
|---|---|---|
| mitdb/100 MLII (650 000 éch.) | −22131 | −22131 |
| mitdb/100 V5 (650 000 éch.) | 20052 | 20052 |
| bidmc01 RESP / PLETH / V / AVR / II | 5854 / 29272 / −17810 / −20589 / 23277 | identiques |

---

## 5. Régénérer les données

```sh
python3 data/fetch.py                 # les trois jeux
python3 data/fetch.py --db mitdb      # un seul jeu
python3 data/fetch.py --dest /tmp/rec # autre destination
```

Politesse du script : ≥ 2 s entre deux requêtes, ≤ 3 tentatives par fichier
(repli exponentiel 2 s puis 4 s), **jamais** de re-téléchargement d'un
fichier déjà présent et vérifié (cache sur l'empreinte publiée), journal
complet dans `data/records/fetch.log`. Chaque fichier téléchargé est vérifié
contre le `SHA256SUMS.txt` publié, sinon il est supprimé.

`data/records/` est **ignoré par git** (données lourdes) : seul `data/fetch.py`
est versionné. Un poste sans réseau ne peut donc pas exécuter les tests
données réelles : les tests se **sautent** proprement (jamais d'échec réseau).

---

## 6. Valeurs réellement lues (extraits vérifiés)

- **mitdb/100 MLII** — 10 premiers entiers bruts :
  `995, 995, 995, 995, 995, 995, 995, 995, 1000, 997`
  → valeurs physiques `(brut − 1024) / 200` : **−0,145 mV** (×8), −0,120 mV,
  −0,135 mV. **`V5`** : `1011, 1011, …` → **−0,065 mV**.
- **bidmc01** (5 signaux × 60 001 éch.) — `RESP` −9577 → **0,35386 pm** ;
  `PLETH` −3446 → **0,43597 NU** ; `II` (ECG) 7335 → **0,72548 mV**, plage
  mesurée **−0,502 à 1,504 mV**.
- **bidmc_01_Numerics.csv** — 481 lignes (t = 0…480 s) ; t = 0 :
  **HR 94, PULSE 93, RESP 25, SpO2 97** ; SpO2 mesurée **96–98 %** (13
  secondes à `NaN` : le moniteur ne rapportait pas la valeur), HR **88–95 bpm**.
- **slp02a BP** — premier brut 41 → **(41 + 513) / 5,06061 = 109,47 mmHg** ;
  ECG premier brut 4 → **−0,008 mV** (gain −500 ADU/mV).
- **bpm dérivés de l'ECG réel** (détection de pics R, §7) :
  - `mitdb/100 MLII`, 100 s : **123 pics R**, bpm moyen **74,0**
    (min 62,1 — max 82,4) — cohérent avec le rythme sinusal normal du
    enregistrement 100 de MIT-BIH.
  - `bidmc01 II` (480 s) : **730 pics R**, bpm moyen **91,7** contre
    **91,3 bpm** de moyenne HR dans le CSV numérique du même patient
    (écart médian par battement : **3 bpm**).

---

## 7. Commandes

Rejeu d'un signal réel dans la chaîne (verdicts rendus par `veille.report`) :

```sh
PYTHONPATH=host python3 -m veille.replay --record data/records/mitdb/100 \
    --signal MLII --format texte          # --format json|markdown
PYTHONPATH=host python3 -m veille.replay --record data/records/bidmc/bidmc01 \
    --signal PLETH --limite 6000 --fenetre 1
```

`--limite N` borne le nombre d'échantillons rejoués (tests, cible QNX),
`--fenetre` la durée de la fenêtre d'analyse (1 s par défaut), `--preuve`
ajoute l'exploration exhaustive de l'espace de défaillance à la fin du rejeu.

Alimentation du resource manager à partir de l'ECG réel :

```sh
# sur l'hôte : écriture dans un fichier (le resource manager est simulé)
PYTHONPATH=host python3 -m veille.resmgr_client --record data/records/mitdb/100 \
    --signal MLII --sortie /tmp/veille.out
# sur la cible QNX : le resource manager possède déjà /dev/veille
PYTHONPATH=host python3 -m veille.resmgr_client --record data/records/mitdb/100 \
    --signal MLII --sortie /dev/veille --temps-reel
```

Chaque battement détecté produit une ligne `bpm <valeur>\n` (valeur entière,
arrondie) ; `--temps-reel` espace les écritures selon l'intervalle R-R réel.

---

## 8. Limites (à lire avant toute citation)

1. **Les annotations `.atr` ne sont PAS parsées.** MIT-BIH publie la vérité
   terrain des arythmies (`100.atr`, `105.atr` : battements R, A, V, F, …) ;
   le code Veille ne les lit **pas encore**. Conséquence directe : les
   extrasystoles ventriculaires de l'enregistrement 105 **ne sont pas
   distinguées**, le bpm publié est un bpm moyen (les PVC sont exclues par
   les intervalles implausibles, pas par leur nature), et il n'est pas encore
   possible de rejouer « une arythmie » de bout en bout avec sa vérité
   terrain. C'est le premier chantier naturel après ce lot.
2. **La détection de pics R est un algorithme simple et non clinique** :
   dérivée → carrure → intégration glissante (150 ms) → seuil adaptatif
   `NPK + 0,25·(SPK − NPK)` → réfractaire 200 ms, sans bibliothèque. Les
   deux ou trois premières valeurs de bpm (seuil en cours d'adaptation) et
   les intervalles très courts ou très longs sont peu fiables. Validation
   empirique disponible : écart médian de **3 bpm** au HR publié par BIDMC
   pour le même patient.
3. **Le diagnostic d'état du capteur est heuristique** (fenêtre constante →
   bloqué/mort, pas médian vs amplitude → bruité, dérive de médiane → dérive).
   Aucun seuil n'est validé cliniquement.
4. **Trois jeux, trois patients différents** (§1.1) : aucune affirmation
   « ECG + SpO2 + PA du même patient » n'est possible avec ces données.
5. **Formats supportés : 212 et 16 uniquement.** Ni 80/61/24/32 bits, ni
   enregistrements multi-segments, ni annotations, ni signaux à fréquences
   différentes dans un même enregistrement.
6. **Le rendu Markdown** affiche « exploration exhaustive de 0 états » tant
   que `--preuve` n'est pas demandé : le rejeu ne fait pas la preuve
   exhaustive (qui reste dans `veille.cli proof`), il montre que des données
   réelles traversent la chaîne et que la latence calculée tient la borne
   **dans l'état observé**.
7. **Les bornes IEC 60601-1-8 restent des ordres de grandeur**
   (`CONTRACT.md` §3) : un rejeu sur données réelles ne démontre aucune
   conformité normative.
8. **Données de recherche, anonymisées** : MIT-BIH est anonymisé ; les
   en-têtes BIDMC indiquent âge, sexe et unité de soins, sans identité.
   Aucune donnée identifiante n'est présente, mais ces jeux restent des
   données de patients réels : usage de recherche uniquement.
