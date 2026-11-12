#!/usr/bin/env python3
"""Construction du site statique Veille.

Un seul gabarit HTML, un seul convertisseur markdown, des helpers partagés
par les deux modules de pages (`pages_md`, `pages_generees`) via un contexte.

Usage : python3 site/build.py [répertoire_sortie]     (défaut : site/_site)
Dépendance : `markdown` (épinglé 3.5.2 dans .github/workflows/pages.yml).
"""
import shutil
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import markdown as md_lib

RACINE = Path(__file__).resolve().parent.parent
EXTENSIONS = ["tables", "fenced_code", "toc", "sane_lists"]
# Ordre de la navigation : source unique, les modules produisent dans l'ordre qu'ils veulent.
ORDRE_NAV = [
    "index", "cahier", "contrat", "codelab", "code", "preuves", "scene", "ci",
    "docs-qnx-evidence", "docs-qnx-build", "docs-real-data", "docs-idees",
    "docs-safety", "docs-gap", "docs-decisions", "docs-validation",
    "docs-iec", "docs-socle-ci",
    "docs-limits", "docs-soumission", "docs-video", "docs-terrain", "docs-matrice",
]

# Pages dont le document source peut ne pas encore exister (il est produit sur
# d'autres branches) : le générateur les ignore alors sans casser le build.
SLUGS_FACULTATIFS = {
    "docs-limits", "docs-soumission", "docs-video", "docs-terrain", "docs-matrice",
}

GABARIT = """<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{titre} — Veille</title>
<link rel="stylesheet" href="style.css">
{extra_head}
</head>
<body>
<header class="top">
<h1>Veille 🩺 <small>moniteur patient QNX 8.0 — latence capteur→alarme bornée et prouvée</small></h1>
<p>QNX Global Hackathon 2026 · Robotics &amp; Medical · 4800 états de défaillance explorés ·
contrat gelé v0.2 · rapports empreintés SHA-256 (IEC 62304)</p>
</header>
<nav>
{nav}
</nav>
<main>
{corps}
</main>
<footer class="pied">Veille — licence MIT · site généré par <code>site/build.py</code> ·
<a href="https://github.com/Tradoooo/veille">dépôt GitHub</a> ·
publié sur <a href="https://tradoooo.github.io/veille/">tradoooo.github.io/veille</a></footer>
</body>
</html>
"""


def _fichiers_src(dossier, suffixes):
    """Fichiers source d'un dossier (triés), sans __pycache__ ni artefacts."""
    racine = RACINE / dossier
    if not racine.is_dir():
        return []
    return sorted(
        p for p in racine.rglob("*")
        if p.is_file() and p.suffix in suffixes and "__pycache__" not in p.parts
    )


def creer_ctx():
    """Contexte partagé : racine + helpers (aucune duplication dans les modules)."""
    ctx = SimpleNamespace()
    ctx.racine = RACINE

    def md(texte):
        return md_lib.markdown(texte, extensions=EXTENSIONS)

    def lire(*chemin):
        return (RACINE.joinpath(*chemin)).read_text(encoding="utf-8")

    def existe(*chemin):
        return RACINE.joinpath(*chemin).exists()

    def fichiers(dossier, suffixes=(".c", ".h", ".py", ".json")):
        return _fichiers_src(dossier, suffixes)

    def lignes(fichier):
        return len(Path(fichier).read_text(encoding="utf-8").splitlines())

    def executer(commande, timeout=120):
        """Sortie RÉELLE d'une commande : (rc, stdout+stderr). Jamais d'exception."""
        try:
            proc = subprocess.run(commande, cwd=RACINE, capture_output=True,
                                  text=True, timeout=timeout)
            return proc.returncode, (proc.stdout + proc.stderr).strip()
        except Exception as exc:  # échec affiché explicitement, jamais caché
            return -1, f"commande impossible : {exc}"

    ctx.md = md
    ctx.lire = lire
    ctx.existe = existe
    ctx.fichiers = fichiers
    ctx.lignes = lignes
    ctx.executer = executer
    return ctx


def construire_nav(pages, actif):
    """Une seule nav pour toutes les pages ; l'entrée courante est marquée .actif."""
    trie = sorted(pages, key=lambda p: ORDRE_NAV.index(p["slug"]))
    return "\n".join(
        f'<a href="{p["slug"]}.html" class="actif">{p["nav"]}</a>'
        if p["slug"] == actif else f'<a href="{p["slug"]}.html">{p["nav"]}</a>'
        for p in trie
    )


def ecrire_page(page, nav_html, sortie):
    """Applique le gabarit unique et écrit <slug>.html ; vérifie que c'est non vide."""
    html = GABARIT.format(titre=page["titre"], nav=nav_html,
                          corps=page["corps_html"],
                          extra_head=page.get("extra_head", ""))
    cible = sortie / f"{page['slug']}.html"
    cible.write_text(html, encoding="utf-8")
    if not html.strip():
        raise SystemExit(f"page vide générée : {cible}")
    return len(html)


def main(argv):
    t0 = time.time()
    sortie = Path(argv[1]) if len(argv) > 1 else RACINE / "site" / "_site"
    if not sortie.is_absolute():
        sortie = RACINE / sortie
    sortie.mkdir(parents=True, exist_ok=True)

    ctx = creer_ctx()
    import pages_generees
    import pages_md
    import pages_scene
    pages = pages_md.construire(ctx) + pages_generees.construire(ctx) \
        + pages_scene.construire(ctx)

    slugs = [p["slug"] for p in pages]
    manquants = [s for s in ORDRE_NAV
                 if s not in slugs and s not in SLUGS_FACULTATIFS]
    if manquants:
        raise SystemExit(f"pages manquantes : {manquants}")

    for page in pages:
        page["corps_html"] = page["corps"] if page.get("html") else ctx.md(page["corps"])
        nav_html = construire_nav(pages, page["slug"])
        taille = ecrire_page(page, nav_html, sortie)
        print(f"[site] {page['slug']}.html — {taille} octets")

    for asset in ("style.css", "scene.css", "scene.js", "data-reel.js"):
        src = RACINE / "site" / asset
        if src.is_file():
            shutil.copyfile(src, sortie / asset)
    duree = time.time() - t0
    print(f"[site] {len(pages)} pages + assets → {sortie} en {duree:.1f} s")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
