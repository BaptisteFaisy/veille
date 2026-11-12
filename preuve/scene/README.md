# Scène « Rejeu réel » — preuves de rendu

Captures headless de la page `scene.html` (scène animée qui rejoue un extrait
d'ECG réel dans la chaîne d'alarme Veille). Chaque capture est figée via le
paramètre d'URL `?t=<seconde>&pause=1` :

| Fichier | Instant | Ce que montre la scène |
|---|---|---|
| `episode-t-0.6-alarme.png` | t = 0,6 s | premier franchissement du seuil (bpm filtré 124,7 > 120) → alarme |
| `episode-t-10.9-svta.png` | t = 10,9 s | annotation de rythme `(SVTA` (tachycardie) sur le tracé |
| `episode-t-27.6-alarme.png` | t = 27,6 s | second franchissement (bpm filtré 122 > 120) + verdict/latence |

## Ce qui est affiché (éléments animés)

1. **Signal brut** — tracé ECG `MLII` du patient réel (MIT-BIH 222, 360 Hz),
   bande défilante sur les 6 dernières secondes (pré-roll de 6 s inclus).
2. **Cadence cardiaque** — bpm instantané (points gris, déduits des pics R) et
   bpm filtré (trait menthe, moyenne glissante de 8), avec le **seuil d'alarme
   120 bpm** en pointillés et les zones au-dessus du seuil surlignées.
3. **Décision** — état courant (`Sous le seuil` / `Alarme haute — seuil franchi`
   / `Alarme technique — capteur figé`), avec le **code de verdict**
   (`VEILLE_OK`, `VEILLE_TECHNICAL_ALARM`) et le seuil + bpm lu/filtré.
4. **Latence** — latence mesurée par la **chaîne C réelle** (harnais
   `target/pipe/veille_pipe.c` + `target/port/host_time.c`) face à la **borne
   prouvée 200 ms** (exploration exhaustive des 4800 états) ; barre = part de
   la borne consommée.
5. **Annotations** — annotations de rythme de la base MIT-BIH (`(AFIB`, `(SVTA`,
   `(NOD`, `(AFL`, `(N`) étiquetées sur la timeline, présentées comme venant des
   annotations officielles.
6. **Légende + source/licence** — provenance (PhysioNet), licence ODC-By 1.0,
   citations Goldberger 2000 et MIT-BIH 1999, mention « données réelles, accès
   libre (ODC-By) ».

## Données embarquées et provenance

- Extrait dérivé de l'enregistrement **MIT-BIH 222** (dérivation `MLII`,
  fibrillation atriale + épisode de tachycardie), fenêtre 705→737 s.
- Licence **ODC-By 1.0** ; les `.dat`/`.atr` complets ne sont **pas** committés
  (`data/records/` est ignoré). Seul l'extrait nécessaire est embarqué dans
  `site/data-reel.js`.
- Régénération : `python3 tools/genere-scene.py` (lit le jeu local, réutilise
  `host/veille/wfdb.py` et `host/veille/resmgr_client.py`, compile un harnais C
  temporaire pour mesurer la latence).

## Régénération complète du site

```sh
python3 tools/genere-scene.py                # → site/data-reel.js
python3 site/build.py /tmp/veille-site       # → 18 pages + assets
```

## Vérifications faites

- `node --check site/scene.js` et `node --check site/data-reel.js` → syntaxe OK.
- `python3 site/build.py` → 18 pages non vides, sans erreur (les 5 documents
  absents `LIMITS/SOUBMISSION/VIDEO/TERRAIN/MATRICE` sont ignorés proprement).
- Rendu vérifié par CDP : DOM mis à jour (décision = « Alarme haute — seuil
  franchi », verdict `VEILLE_OK`, latence 1 µs ≤ 200 ms) et pixels réellement
  tracés dans les deux canvas (19 059 px ECG, 29 940 px bpm).

## Procédure de capture

```sh
# navigateur headless (chromium) — figer l'épisode à l'instant t :
google-chrome --headless --no-sandbox --disable-gpu \
  --window-size=1080,1580 --screenshot=scene.png \
  "file:///tmp/veille-site/scene.html?t=27.6&pause=1"
```