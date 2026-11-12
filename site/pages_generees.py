#!/usr/bin/env python3
"""Pages GÉNÉRÉES depuis le dépôt réel : code, preuves, CI. Rien n'est recopié
à la main : volumétrie, API, verdicts, scénarios et sorties de commande sont
lus/exécutés à chaque génération. Un échec est affiché explicitement."""
import json
import re
from html import escape

DOSSIERS = ["core", "host", "tests", "scenarios", "target"]
SUFFIXES = (".c", ".h", ".py", ".json")


def esc(texte):
    """Échappement HTML (textes du dépôt = code non fiable)."""
    return escape(str(texte), quote=False)


def tableau(entetes, lignes, classes=""):
    """Unique générateur de tableau HTML partagé par toutes les pages générées."""
    out = [f'<table class="{classes}">',
           "<tr>" + "".join(f"<th>{esc(h)}</th>" for h in entetes) + "</tr>"]
    for ligne in lignes:
        out.append("<tr>" + "".join(f"<td>{cellule}</td>" for cellule in ligne) + "</tr>")
    out.append("</table>")
    return "\n".join(out)


def arborescence(ctx):
    """Volumétrie réelle : fichiers source par répertoire + total de lignes."""
    blocs = []
    for dossier in DOSSIERS:
        fichiers = ctx.fichiers(dossier, SUFFIXES)
        if not fichiers:
            continue
        lignes = [(f"<code>{esc(f.relative_to(ctx.racine))}</code>", str(ctx.lignes(f))) for f in fichiers]
        total = sum(int(n) for _, n in lignes)
        lignes.append((f"<b>total {esc(dossier)}/</b>", f"<b>{total}</b>"))
        blocs.append(f"<h3>{esc(dossier)}/ — {len(fichiers)} fichiers, {total} lignes</h3>")
        blocs.append(tableau(["Fichier", "Lignes"], lignes, "arbre"))
    return "\n".join(blocs)


def api_c(ctx):
    """API C extraite des en-têtes de core/include/veille/ (prototypes + typedefs)."""
    blocs = []
    for entete in ctx.fichiers("core/include/veille", (".h",)):
        texte = " ".join(entete.read_text(encoding="utf-8").split())
        protos = re.findall(r"([A-Za-z_][\w\* ]*?)\b(veille_\w+)\s*\(([^;]*?)\)\s*;", texte)
        typedefs = re.findall(r"\}\s*(veille_\w+)\s*;", texte)
        blocs.append(f"<h3>{esc(entete.name)}</h3>")
        if typedefs:
            blocs.append('<p class="desc">Types : ' + ", ".join(
                f"<code>{esc(t)}</code>" for t in typedefs) + "</p>")
        lignes = [(f"<code>{esc(r.strip())} {esc(n)}({esc(a.strip())})</code>") for r, n, a in protos]
        blocs.append(tableau(["Prototype"], lignes))
    return "\n".join(blocs)


def modules_py(ctx):
    """Modules Python de host/veille/ : rôle (docstring) + fonctions définies."""
    blocs = []
    for module in ctx.fichiers("host/veille", (".py",)):
        texte = module.read_text(encoding="utf-8")
        entete = re.search(r'"""(.*?)"""', texte, re.DOTALL)
        doc = entete.group(1).strip().splitlines()[0] if entete and entete.group(1).strip() else ""
        defs = re.findall(r"^def (\w+)", texte, re.MULTILINE)
        classes = re.findall(r"^class (\w+)", texte, re.MULTILINE)
        blocs.append(f"<h3>{esc(module.name)} — {len(defs)} fonctions, {len(classes)} classes</h3>")
        if doc:
            blocs.append(f'<p class="desc">{esc(doc)}</p>')
        if defs:
            blocs.append("<p>" + ", ".join(f"<code>{esc(d)}()</code>" for d in defs) + "</p>")
    return "\n".join(blocs)


def cibles_make(ctx):
    """Cibles du Makefile lues dans le Makefile (hors variables `:=` et .PHONY)."""
    cibles = []
    for ligne in ctx.lire("Makefile").splitlines():
        match = re.match(r"^([A-Za-z_][\w.\-/%]*):(?!=)\s*(.*)$", ligne)
        if match and not match.group(1).startswith("."):
            cibles.append((f"<code>{esc(match.group(1))}</code>", esc(match.group(2).strip())))
    return cibles


def page_code(ctx):
    """Page « Code » : tout est mesuré dans le dépôt."""
    corps = "\n".join([
        "<h1>Code source</h1>",
        '<p class="desc">Volumétrie, API et cibles de build calculées à chaque '
        "génération du site depuis le dépôt réel.</p>",
        "<h2>Arborescence et volumétrie</h2>",
        arborescence(ctx),
        "<h2>API C — core/include/veille/</h2>",
        api_c(ctx),
        "<h2>Modules Python — host/veille/</h2>",
        modules_py(ctx),
        "<h2>Cibles du Makefile</h2>",
        tableau(["Cible", "Dépendances / recette"], cibles_make(ctx)),
    ])
    return {"slug": "code", "nav": "Code", "titre": "Code source",
            "corps": corps, "html": True}


def verdicts(ctx):
    """Les 10 codes de verdict extraits de core/include/veille/verdict.h."""
    texte = ctx.lire("core/include/veille/verdict.h")
    bloc = re.search(r"typedef enum \{(.*?)\}\s*veille_verdict_code;", texte, re.DOTALL)
    if not bloc:
        return []
    noms = re.findall(r"\bVEILLE_[A-Z][A-Z_]*\b", bloc.group(1))
    return [n for n in noms if not n.endswith("__COUNT")]


def scenarios(ctx):
    """Corpus réel scenarios/*.json : contenu synthétique de chaque scénario."""
    items = []
    for fichier in ctx.fichiers("scenarios", (".json",)):
        data = json.loads(fichier.read_text(encoding="utf-8"))
        attendu = data.get("expected", {})
        items.append({"fichier": fichier.name, "description": data.get("description", ""),
                      "priorite": data.get("priority"), "borne": data.get("bound_alarm_ms"),
                      "tech": data.get("bound_tech_ms"), "rc": attendu.get("rc"),
                      "code": attendu.get("code")})
    return items


def proprietes(ctx):
    """Propriétés prouvées (P1, P2, …) extraites du CONTRAT."""
    return re.findall(r"^### (P\d+) — (.+)$", ctx.lire("CONTRACT.md"), re.MULTILINE)


def bloc_commande(commande, rc, sortie, note="", etat=None):
    """Un bloc commande : rc + sortie RÉELS ; tout échec est affiché."""
    etat = etat or ("ok" if rc == 0 else "echec")
    etiquettes = {"ok": "rc=0 · OK", "echec": f"rc={rc} · ÉCHEC", "attendu": f"rc={rc} · échec attendu"}
    note_html = f'<p class="desc">{note}</p>' if note else ""
    return ('<div class="cmd"><div class="entete">'
            f"<b>$ {esc(commande)}</b>"
            f'<span class="etat {etat}">{etiquettes[etat]}</span></div>'
            f"<pre>{esc(sortie)}</pre>{note_html}</div>")


def verdicts_html(ctx):
    codes = verdicts(ctx)
    items = "".join(f"<li>{esc(c)} <i>#{i}</i></li>" for i, c in enumerate(codes))
    return (f'<p class="desc">Extraits de <code>core/include/veille/verdict.h</code> '
            f"(ordre figé par le contrat) : {len(codes)} codes.</p>"
            f'<ul class="verdicts">{items}</ul>')


def scenarios_html(ctx):
    lignes = []
    for it in scenarios(ctx):
        desc = it["description"]
        if len(desc) > 260:
            desc = desc[:257] + "…"
        lignes.append((f"<code>{esc(it['fichier'])}</code>", esc(desc),
                       f"P{it['priorite']}", f"{it['borne']} ms",
                       f"{it['tech']} ms" if it["tech"] else "—",
                       f"rc={it['rc']} · <code>{esc(it['code'])}</code>"))
    return tableau(["Fichier", "Description", "Prio", "Borne alarme",
                    "Borne tech", "Verdict attendu"], lignes)


def sorties_reelles(ctx):
    """Exécute les commandes au moment de la génération : rien n'est simulé."""
    rc, out = ctx.executer(["make", "-s", "demo"], 120)
    blocs = [bloc_commande("make -s demo", rc, out, "Simulation hôte : preuve modèle + mesure empirique.")]
    rc, out = ctx.executer(["make", "-s", "proof"], 120)
    blocs.append(bloc_commande("make -s proof", rc, out,
                               "Exploration du sous-ensemble S4 (cible Makefile)."))
    rc, out = ctx.executer(["env", "PYTHONPATH=host", "python3", "-m",
                            "veille.cli", "proof"], 120)
    blocs.append(bloc_commande(
        "PYTHONPATH=host python3 -m veille.cli proof", rc, out,
        "Exploration exhaustive des 4800 états sur la borne haute 100 ms : le pire cas "
        "dépasse la borne et produit un contre-exemple — comportement <b>attendu et déclaré</b> "
        "par le corpus (<code>scenarios/high_nominal.json</code> exige <code>rc=1</code> / "
        "<code>VEILLE_PROOF_COUNTEREXAMPLE</code>). C'est l'objet même de la preuve.",
        etat="attendu" if rc == 1 else None))
    return "\n".join(blocs)


def page_preuves(ctx):
    props = "".join(f"<li><b>{esc(n)}</b> — {esc(t)}</li>" for n, t in proprietes(ctx))
    corps = "\n".join([
        "<h1>Preuves</h1>",
        '<div class="bandeau">Double preuve : <b>modèle</b> (exploration exhaustive '
        "des états de défaillance, C11 pur + jumeau Python, test différentiel) et "
        "<b>empirique</b> (kernel trace sur cible QNX). Rapports texte/JSON/Markdown "
        "empreintés SHA-256 pour dossier IEC 62304.</div>",
        "<h2>Propriétés prouvées (contrat v0.2)</h2>", f"<ul>{props}</ul>",
        "<h2>Les codes de verdict</h2>", verdicts_html(ctx),
        "<h2>Corpus de scénarios de défaillance</h2>", scenarios_html(ctx),
        "<h2>Sorties réelles (exécutées à la génération du site)</h2>",
        sorties_reelles(ctx),
    ])
    return {"slug": "preuves", "nav": "Preuves", "titre": "Preuves",
            "corps": corps, "html": True}


def workflows(ctx):
    """Workflows du dépôt : fichier → nom, lus dans .github/workflows/."""
    items = []
    dossier = ctx.racine / ".github" / "workflows"
    for fichier in sorted(dossier.glob("*.yml")):
        match = re.search(r"^name:\s*(.+)$", fichier.read_text(encoding="utf-8"),
                          re.MULTILINE)
        items.append((fichier.name, match.group(1).strip() if match else fichier.stem))
    return items


def page_ci(ctx):
    lignes = ["| Workflow | Nom | Runs |", "|---|---|---|"]
    for nom_fichier, nom in workflows(ctx):
        url = f"https://github.com/BaptisteFaisy/veille/actions/workflows/{nom_fichier}"
        lignes.append(f"| `{nom_fichier}` | {nom} | [voir les runs]({url}) |")
    corps = "\n\n".join([
        "# CI & socle self-hosted",
        "![Badge CI](https://github.com/BaptisteFaisy/veille/actions/workflows/ci.yml/badge.svg)",
        "## Le socle (R630)",
        "- **3 workers self-hosted** `r630-veille-01..03` (label `veille-worker`, "
        "Debian 13, 80 cœurs) : gcc/python3/make déjà présents, aucun apt-get en CI.",
        "- **Garde `ci-budget`** : chaque job GitHub Actions déclare "
        "`timeout-minutes: 5` au plus (`.github/ci-budget/check_timeouts.py`), avec "
        "`concurrency` + `cancel-in-progress` et `fetch-depth: 1`. Le check "
        "`ci-budget` est exigé par la file de merge.",
        "- **Mergify est le seul pilote du merge** : file de merge, rebase, "
        "batching 1–3, conditions `ci-budget` + `build-test` verts, base `main`, "
        "labels `urgent` / `priority-low`.",
        "- **Gate `hermes-lite` en dry-run** (`HERMES_LITE_DRY_RUN=1`) : il évalue "
        "et étiquette (`hermes/approuvee`, `hermes/conflit`), il ne merge jamais.",
        "- **`stale-base-guard`** : check informatif de retard de branche.",
        "- **Pages** : ce site est construit et publié par "
        "`.github/workflows/pages.yml` (push sur `main` + `workflow_dispatch`), "
        "avec `markdown==3.5.2` épinglé.",
        "## Workflows du dépôt (liste générée)",
        "\n".join(lignes),
        "## Liens stables",
        "- Tous les runs : <https://github.com/BaptisteFaisy/veille/actions>",
        "- File de merge / PR : <https://github.com/BaptisteFaisy/veille/pulls>",
    ])
    return {"slug": "ci", "nav": "CI & socle", "titre": "CI & socle", "corps": corps}


def construire(ctx):
    """Les trois pages générées : code, preuves, CI."""
    return [page_code(ctx), page_preuves(ctx), page_ci(ctx)]
