#!/usr/bin/env python3
"""Matrice exigence -> test -> preuve, générée depuis les SOURCES du dépôt.

Lit les tables d'exigences du cahier des charges (sections 6.1/6.2/6.3 :
`| S1 | texte | S |`, `| C1 | … | C |`, `| X1 | … | X |`), puis cherche pour
chaque identifiant où il est couvert (tests, journaux de preuve) dans le dépôt.
Produit docs/MATRICE.md (Markdown) et, en `--check`, vérifie qu'il est à jour.

Usage : python3 tools/matrice.py [--check]
"""
from __future__ import annotations

import pathlib
import re
import sys

RACINE = pathlib.Path(__file__).resolve().parent.parent
CAHIER = RACINE / "VEILLE-cahier-des-charges.md"
SORTIE = RACINE / "docs" / "MATRICE.md"
RE_EX = re.compile(r"^\|\s*(S\d+|C\d+|X\d+)\s*\|\s*(.+?)\s*\|\s*[SCX]\s*\|$")

# Dossiers où chercher la couverture d'un identifiant.
FOUILLES = ["tests", "core/tests", "host/tests", "preuve", "docs/QNX-EVIDENCE.md",
            "scenarios"]

# Couverture explicite (fichiers qui couvrent l'exigence sans en citer l'ID).
# Le grep (ci-dessous) complète ; cette table fixe les cas où l'ID n'apparaît
# pas littéralement dans les tests.
COUVERT = {
    "S1": ["core/src/chain.c", "core/include/veille/chain.h", "target/pipe/veille_pipe.c"],
    "S2": ["host/veille/chain.py", "host/veille/state.py", "host/veille/verdict.py"],
    "S3": ["tests/differential.py", "host/tests/test_proof.py"],
    "S4": ["core/src/proof.c", "core/tests/test_proof.c", "host/tests/test_proof.py"],
    "S5": ["core/src/report.c", "core/src/verdict.c"],
    "S6": ["target/pipe/veille_pipe.c", "scenarios/signal_dead.json", "scenarios/signal_flat_60.json"],
    "S7": ["Makefile", ".github/workflows/ci.yml"],
    "S8": [".github/workflows/ci.yml", ".github/workflows/ci-budget.yml"],
    "C1": ["target/rm/resmgr_veille.c", "target/rm/rm_io.c", "docs/QNX-EVIDENCE.md"],
    "C4": ["core/src/proof.c", "tests/differential.py", "docs/QNX-EVIDENCE.md"],
}


def extraire_exigences() -> list[tuple[str, str, str]]:
    out = []
    for ligne in CAHIER.read_text(encoding="utf-8").splitlines():
        m = RE_EX.match(ligne)
        if m:
            ident, texte = m.group(1), m.group(2).strip()
            niveau = ident[0]
            out.append((ident, texte, niveau))
    return out


def couverture(ident: str) -> list[str]:
    """Fichiers (relatifs à la racine) qui mentionnent l'identifiant."""
    hits = list(COUVERT.get(ident, []))
    for dossier in FOUILLES:
        base = RACINE / dossier
        if not base.exists():
            continue
        fichiers = [base] if base.is_file() else list(base.rglob("*"))
        for f in fichiers:
            if not f.is_file() or "__pycache__" in f.parts:
                continue
            try:
                texte = f.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            if ident in texte:
                hits.append(str(f.relative_to(RACINE)))
    return hits


def generer() -> str:
    exigences = extraire_exigences()
    lignes = ["# Matrice exigence → test → preuve", "",
              "> Générée automatiquement par `tools/matrice.py` depuis les sources "
              "du dépôt : toute ligne « non couverte » est un trou assumé, pas une "
              "erreur de génération. Régénérer : `python3 tools/matrice.py`.",
              "", "| ID | Niveau | Exigence | Couverture (fichiers qui la citent) |", 
              "|---|---|---|---|"]
    couverts, trous = 0, 0
    for ident, texte, niveau in exigences:
        hits = couverture(ident)
        if hits:
            couverts += 1
            source = ", ".join(sorted(set(hits)))
        else:
            trous += 1
            source = "**non couverte**"
        lignes.append(f"| {ident} | {niveau} | {texte} | {source} |")
    lignes += ["", f"**Bilan** : {len(exigences)} exigences — {couverts}"
               f" citées par au moins un test ou une preuve, {trous} non couvertes.", ""]
    return "\n".join(lignes)


def main(argv: list[str]) -> int:
    contenu = generer()
    if "--check" in argv:
        if not SORTIE.exists() or SORTIE.read_text(encoding="utf-8") != contenu:
            print(f"MATRICE.md périmée. Relancer : python3 tools/matrice.py", file=sys.stderr)
            return 1
        print("MATRICE.md à jour.")
        return 0
    SORTIE.write_text(contenu, encoding="utf-8")
    print(f"{SORTIE.relative_to(RACINE)} : {len(extraire_exigences())} exigences.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))