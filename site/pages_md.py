#!/usr/bin/env python3
"""Pages du site issues des markdown du dépôt (aucun texte recopié à la main)."""
import re

# Liens internes des .md du dépôt → pages du site (évite les liens morts).
LIENS = {
    "README.md": "index.html",
    "CONTRACT.md": "contrat.html",
    "VEILLE-cahier-des-charges.md": "cahier.html",
    "docs/SAFETY.md": "docs-safety.html",
    "docs/GAP.md": "docs-gap.html",
    "docs/DECISIONS.md": "docs-decisions.html",
    "docs/VALIDATION.md": "docs-validation.html",
    "docs/IEC60601-8.md": "docs-iec.html",
    "docs/SOCLE-CI.md": "docs-socle-ci.html",
    "LICENSE": "https://github.com/BaptisteFaisy/veille/blob/main/LICENSE",
}

DOCS = [
    ("SAFETY.md", "docs-safety", "Sûreté"),
    ("GAP.md", "docs-gap", "Écarts"),
    ("DECISIONS.md", "docs-decisions", "Décisions"),
    ("VALIDATION.md", "docs-validation", "Validation"),
    ("IEC60601-8.md", "docs-iec", "IEC 60601-8"),
    ("SOCLE-CI.md", "docs-socle-ci", "Socle CI"),
]


def adapter_liens(texte):
    """Réécrit les liens .md du dépôt vers les pages du site + codelab → codelab.html."""
    for src, dst in LIENS.items():
        texte = texte.replace(f"]({src})", f"]({dst})")
    return re.sub(r"\]\(codelab/[^)]*\)", "](codelab.html)", texte)


def extraire_section(texte, titre):
    """Renvoie le contenu d'une section `## titre` (jusqu'au prochain `## `)."""
    motif = re.compile(rf"^## {re.escape(titre)}\s*$(.*?)(?=^## |\Z)",
                       re.MULTILINE | re.DOTALL)
    match = motif.search(texte)
    return match.group(1).strip() if match else ""


def titre_de(texte, repli):
    """Premier `# titre` du document, sinon le repli donné."""
    match = re.search(r"^# (.+)$", texte, re.MULTILINE)
    return match.group(1).strip() if match else repli


def compter(ctx):
    """Chiffres CALCULÉS depuis le dépôt réel (jamais de valeur recopiée)."""
    c = sum(ctx.lignes(f) for f in ctx.fichiers("core", (".c", ".h")))
    c += sum(ctx.lignes(f) for f in ctx.fichiers("target", (".c",)))
    py = sum(ctx.lignes(f) for f in ctx.fichiers("host", (".py",)))
    py += sum(ctx.lignes(f) for f in ctx.fichiers("tests", (".py",)))
    tests = len(ctx.fichiers("core/tests", (".c",)))
    tests += len([f for f in ctx.fichiers("host/tests", (".py",))
                  if f.name.startswith("test_")])
    tests += len(ctx.fichiers("tests", (".py",)))
    return {"c": c, "py": py, "tests": tests,
            "scenarios": len(ctx.fichiers("scenarios", (".json",)))}


def bornes_table(ctx):
    """Bornes par priorité extraites du tableau du CONTRAT (source de vérité)."""
    contrat = ctx.lire("CONTRACT.md")
    motif = re.compile(r"^\|\s*`?(VEILLE_PRIO_\w+|technique)`?\s*\|"
                       r"\s*(\d+)\s*ms\s*\|\s*([^|]*)\|", re.MULTILINE)
    lignes = ["| Priorité | Borne alarme | Borne acquittement |", "|---|---|---|"]
    for nom, ms, ack in motif.findall(contrat):
        lignes.append(f"| `{nom}` | **{ms} ms** | {ack.strip()} |")
    return "\n".join(lignes)


def page_index(ctx):
    """Accueil : pitch + chiffres clés calculés + tableau d'état du README."""
    readme = ctx.lire("README.md")
    pitch = readme.split("## Pourquoi")[0].replace("# Veille 🩺", "").strip().strip("-").strip()
    chiffres = compter(ctx)
    etats = re.search(r"\*\*(\d+) états\*\*", ctx.lire("CONTRACT.md"))
    cartes = [
        (chiffres["c"], "lignes de C11 (core/ + target/)"),
        (chiffres["py"], "lignes de Python (host/ + tests/)"),
        (chiffres["tests"], "fichiers de tests"),
        (chiffres["scenarios"], "scénarios de référence"),
        (etats.group(1) if etats else "?", "états de défaillance explorés"),
    ]
    html_cartes = '<div class="cartes">' + "".join(
        f'<div class="carte"><b>{v}</b><span>{legende}</span></div>'
        for v, legende in cartes) + "</div>"
    corps = "\n\n".join([
        pitch,
        "## Chiffres clés\n\n<p class=\"desc\">Calculés depuis le dépôt à chaque "
        "génération du site.</p>\n" + html_cartes,
        "## Bornes IEC 60601-1-8 (contrat gelé v0.2)\n\n" + bornes_table(ctx),
        "## État du projet\n" + extraire_section(readme, "État"),
    ])
    return {"slug": "index", "nav": "Accueil", "titre": "Accueil",
            "corps": adapter_liens(corps)}


def concatener_codelab(ctx):
    """Sommaire + les 4 chapitres du codelab, en UNE seule concaténation."""
    fichiers = ["README.md", "01-pourquoi-une-borne-prouvee.md",
                "02-construire-la-chaine.md", "03-prouver-par-exploration.md",
                "04-porter-sur-qnx.md"]
    textes = [ctx.lire("codelab", f) for f in fichiers]
    return adapter_liens("\n\n---\n\n".join(textes)), titre_de(textes[0], "Codelab")


def page_doc(ctx, fichier, slug, nav):
    """Une page par document : contenu intégral du .md du dépôt."""
    texte = ctx.lire("docs", fichier)
    return {"slug": slug, "nav": nav, "titre": titre_de(texte, nav),
            "corps": adapter_liens(texte)}


def construire(ctx):
    """Toutes les pages markdown : accueil, cahier, contrat, codelab, docs."""
    pages = [page_index(ctx)]
    cahier = ctx.lire("VEILLE-cahier-des-charges.md")
    contrat = ctx.lire("CONTRACT.md")
    codelab, titre_codelab = concatener_codelab(ctx)
    pages.append({"slug": "cahier", "nav": "Cahier des charges",
                  "titre": titre_de(cahier, "Cahier des charges"),
                  "corps": adapter_liens(cahier)})
    pages.append({"slug": "contrat", "nav": "Contrat v0.2",
                  "titre": titre_de(contrat, "Contrat"),
                  "corps": adapter_liens(contrat)})
    pages.append({"slug": "codelab", "nav": "Codelab", "titre": titre_codelab,
                  "corps": codelab})
    for fichier, slug, nav in DOCS:
        pages.append(page_doc(ctx, fichier, slug, nav))
    return pages
