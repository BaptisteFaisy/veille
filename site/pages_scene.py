#!/usr/bin/env python3
"""Page « Rejeu réel » : la scène animée (canvas) de l'extrait patient réel.

Une SEULE implémentation de la scène : le code est dans ``site/scene.js`` +
``site/scene.css``, les données dans ``site/data-reel.js`` (produit par
``tools/genere-scene.py``). Cette page fournit le HTML et la légende ; les
autres pages (accueil, preuves) n'y renvoient que par un lien — pas de
deuxième copie de la scène.
"""
import json

# Encadré « Rejouer un épisode réel » réutilisé par l'accueil et les preuves.
ENCADRE = (
    '<div class="bandeau"><b>Rejouer un épisode réel</b> — une scène animée '
    "rejoue <b>32 s d'ECG d'un patient réel</b> (MIT-BIH 222, fibrillation "
    "atriale) dans la chaîne capteur→alarme : signal brut qui défile, seuil "
    "d'alarme franchi, code de verdict et latence mesurée face à la borne "
    'prouvée. <a class="btn-rejeu" href="scene.html">Ouvrir la scène →</a>'
    "</div>"
)


def encadre_rejeu():
    """Encadré d'appel vers la scène (source unique, utilisé par 2 pages)."""
    return ENCADRE


def lire_reel(ctx):
    """Métadonnées de l'extrait embarqué, lues dans ``site/data-reel.js``.

    Le fichier est ``window.VEILLE_REEL = {…};`` : on retire l'affectation et
    on désérialise le JSON. ``None`` si l'extrait n'a pas encore été généré.
    """
    chemin = ctx.racine / "site" / "data-reel.js"
    if not chemin.is_file():
        return None
    texte = chemin.read_text(encoding="utf-8")
    try:
        return json.loads(texte[texte.index("=") + 1:texte.rindex(";")])
    except (ValueError, json.JSONDecodeError):
        return None


def _legende():
    """Légende du tracé (une seule fois, ici)."""
    items = [
        ("trait menthe", "bpm filtré — moyenne glissante de 8 échantillons "
                         "(identique au filtre de la chaîne)"),
        ("points gris", "bpm instantané déduit de l'ECG réel (pics R)"),
        ("pointillés roses", "seuil d'alarme haute priorité (120 bpm)"),
        ("fond rose", "bpm filtré au-dessus du seuil → alarme déclenchée"),
        ("traits orange", "annotations de rythme MIT-BIH ((AFIB, (SVTA)…)"),
        ("bande supérieure", "signal brut ECG (MLII, 360 Hz) — 6 dernières secondes"),
    ]
    return ("<ul>" + "".join("<li><b>%s</b> — %s</li>" % (a, b)
                             for a, b in items) + "</ul>")


def _source(reel):
    """Bloc source / licence / citations, issu des métadonnées de l'extrait."""
    if not reel:
        return ('<p class="src">Extrait non généré : lancer '
                "<code>python3 tools/genere-scene.py</code>.</p>")
    src = reel["source"]
    cites = "".join("<li>%s</li>" % c[1] for c in src.get("citations", []))
    return (
        "<p class=\"src\"><b>Source</b> — %s, enregistrement <code>%s</code>, "
        "dérivation <code>%s</code>, %d Hz. Fenêtre rejouée : %g→%g s.</p>"
        "<p class=\"src\"><b>Licence</b> — %s (<a href=\"%s\">%s</a>). "
        "<b>Données réelles, accès libre (ODC-By).</b></p>"
        "<p class=\"src\"><b>Citations exigées par la licence</b></p><ul>%s</ul>"
        "<p class=\"src\"><em>%s</em></p>"
        % (src["base"], src["record"], src["signal"], src["fs"],
           src["t0"], src["t0"] + src["duree"], src["licence"],
           src["licence_url"], src["licence_url"], cites, src.get("note", "")))


def _scene_html():
    """Structure HTML de la scène (canvas unique par tracé + panneaux)."""
    return """
<div class="scene-bar">
  <button type="button" id="scene-play" class="actif">Pause</button>
  <button type="button" id="scene-restart">Recommencer</button>
  <label for="scene-speed">Vitesse
    <select id="scene-speed">
      <option value="0.5">0,5×</option>
      <option value="1" selected>1×</option>
      <option value="2">2×</option>
      <option value="4">4×</option>
    </select>
  </label>
  <span class="horo" id="scene-horo">t = 0 s</span>
</div>

<div class="trace">
  <h3>Signal brut — ECG (MLII) du patient réel, 6 dernières secondes</h3>
  <canvas id="scene-ecg" data-h="190" role="img"
          aria-label="Tracé ECG défilant du patient réel MIT-BIH 222"></canvas>
</div>

<div class="trace">
  <h3>Cadence cardiaque filtrée, seuil d'alarme et annotations MIT-BIH</h3>
  <canvas id="scene-bpm" data-h="210" role="img"
          aria-label="Courbe de la fréquence cardiaque filtrée avec le seuil d'alarme à 120 bpm et les annotations de rythme MIT-BIH"></canvas>
</div>

<div class="scene-panels">
  <div class="panel" id="scene-decision">
    <h3>Décision de la chaîne</h3>
    <div class="valeur" id="scene-decision-valeur">—</div>
    <div class="verdict" id="scene-decision-verdict">—</div>
    <div class="verdict" id="scene-decision-seuil">—</div>
  </div>
  <div class="panel">
    <h3>Latence mesurée vs borne prouvée</h3>
    <div class="valeur" id="scene-lat-mesuree">—</div>
    <div class="verdict" id="scene-lat-borne">—</div>
    <div class="lat-bar"><div class="lat-fill" id="scene-lat-fill"></div></div>
    <p class="desc">Barre = part de la borne consommée par la latence mesurée.</p>
  </div>
</div>
"""


def page_scene(ctx):
    """La page « Rejeu réel » (HTML pré-calculé, pas de markdown)."""
    reel = lire_reel(ctx)
    corps = "\n".join([
        "<h1>Rejeu réel</h1>",
        '<p class="intro">Cette page rejoue des <strong>données de patient '
        "réelles</strong> dans la chaîne d'alarme Veille : le signal ECG "
        "défile, la cadence cardiaque est filtrée puis comparée au seuil "
        "d'alarme haute priorité, et chaque décision est rendue avec son "
        "<strong>code de verdict</strong> et sa <strong>borne</strong>. "
        "La latence affichée est <strong>mesurée</strong> par la chaîne C "
        "réelle du dépôt, face à la borne prouvée par exploration exhaustive "
        "des 4800 états de défaillance.</p>",
        '<p class="intro">Les données sont <strong>réelles et en accès libre</strong> '
        "(PhysioNet, MIT-BIH Arrhythmia Database, licence ODC-By 1.0). "
        "L'extrait embarqué est un résumé dérivé de l'enregistrement 222 "
        "(fibrillation atriale) : les fichiers originaux ne sont pas "
        "committés, ils sont régénérés par <code>data/fetch.py</code>.</p>",
        _scene_html(),
        '<div class="scene-legend"><b>Légende</b>' + _legende() + "</div>",
        '<div class="scene-legend src"><b>Source et licence</b>' + _source(reel) + "</div>",
        "<noscript><p class=\"desc\">La scène a besoin de JavaScript "
        "(canvas + requestAnimationFrame). Les données et leur provenance "
        "restent lisibles ci-dessus.</p></noscript>",
    ])
    return {
        "slug": "scene", "nav": "Rejeu réel", "titre": "Rejeu réel",
        "corps": corps, "html": True,
        "extra_head": ('<link rel="stylesheet" href="scene.css">\n'
                       '<script src="data-reel.js" defer></script>\n'
                       '<script src="scene.js" defer></script>'),
    }


def construire(ctx):
    """Pages de la scène (une seule : « Rejeu réel »)."""
    return [page_scene(ctx)]
