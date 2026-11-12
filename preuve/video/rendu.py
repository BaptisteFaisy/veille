#!/usr/bin/env python3
"""Rendu des plans de la vidéo Veille (PNG à partir de scenes.tsv).

Rôle : convertir la source unique `scenes.tsv` en diapositives PNG (le montage
s'enchaîne ensuite avec ffmpeg), et produire le tableau de storyboard Markdown
qui alimente `docs/VIDEO.md`.

Usage :
    python3 preuve/video/rendu.py              # génère preuve/video/plans/*.png
    python3 preuve/video/rendu.py --table      # imprime le storyboard Markdown
    python3 preuve/video/rendu.py --liste      # imprime la liste brute des plans

Dépendance : Pillow (PIL). Si absent, le script s'arrête avec un message clair.
"""
import os
import sys

LARGEUR, HAUTEUR = 1280, 720
COULEUR_FOND = (16, 24, 32)          # bleu nuit
COULEUR_TITRE = (240, 244, 248)
COULEUR_TEXTE = (210, 220, 230)
COULEUR_ACCENT = (94, 200, 160)      # accent médical
COULEUR_CODE = (176, 196, 210)
COULEUR_SOUS_TITRE = (255, 214, 102)

RACINE = os.path.dirname(os.path.abspath(__file__))
DOSSIER_CAPTURES = os.path.join(RACINE, "captures")
DOSSIER_PLANS = os.path.join(RACINE, "plans")

FONTS = {
    "titre": "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "corps": "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    "sous": "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
}

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    sys.exit("Pillow absent : installe-le (pip install Pillow) pour générer les plans.")


def charger_scenes(chemin):
    """Lit scenes.tsv et renvoie la liste des plans (dicts)."""
    scenes = []
    with open(chemin, encoding="utf-8") as f:
        for ligne in f:
            ligne = ligne.rstrip("\n")
            if not ligne.strip() or ligne.startswith("#"):
                continue
            duree, titre, narration, source = (p.strip() for p in ligne.split("|||"))
            scenes.append({
                "duree": float(duree),
                "titre": titre,
                "narration": narration,
                "source": source,
            })
    return scenes


def lignes_utiles(nom, limite=12):
    """Lignes « à montrer » d'une capture : sans les commentaires # ni le vide."""
    chemin = os.path.join(DOSSIER_CAPTURES, nom)
    if not os.path.isfile(chemin):
        return [f"(capture absente : {nom})"]
    sorties = []
    with open(chemin, encoding="utf-8") as f:
        for l in f:
            l = l.rstrip("\n").rstrip("\r")
            t = l.strip()
            if not t or t.startswith("#"):
                continue
            sorties.append(l)
    return sorties[:limite]


def taille_fonctionnelle(draw, texte, fonte, largeur_max):
    """Réduit une fonte jusqu'à ce que le texte tienne dans largeur_max."""
    taille = 34
    while taille > 14:
        f = ImageFont.truetype(FONTS["corps"], taille)
        if draw.textlength(texte, font=f) <= largeur_max:
            return f
        taille -= 2
    return ImageFont.truetype(FONTS["corps"], taille)


def envelopper(draw, texte, fonte, largeur_max):
    """Coupe le texte en lignes qui tiennent dans largeur_max (coupe sur espace)."""
    mots = texte.split()
    lignes, courante = [], ""
    for m in mots:
        essai = m if not courante else courante + " " + m
        if draw.textlength(essai, font=fonte) <= largeur_max or not courante:
            courante = essai
        else:
            lignes.append(courante)
            courante = m
    if courante:
        lignes.append(courante)
    return lignes


def dessiner_scene(scene, index):
    """Dessine une diapositive 1280x720 et la sauvegarde dans plans/."""
    img = Image.new("RGB", (LARGEUR, HAUTEUR), COULEUR_FOND)
    d = ImageDraw.Draw(img)
    f_titre = ImageFont.truetype(FONTS["titre"], 46)
    f_sous = ImageFont.truetype(FONTS["sous"], 24)
    # Bandeau supérieur : numéro de plan + titre
    d.rectangle((0, 0, LARGEUR, 96), fill=(24, 40, 56))
    d.text((36, 26), f"{index:02d}", font=f_titre, fill=COULEUR_ACCENT)
    d.text((110, 24), scene["titre"], font=f_titre, fill=COULEUR_TITRE)
    # Corps : texte seul ou contenu d'une capture
    if scene["source"] == "-":
        corps = ["Veille — moniteur patient QNX 8.0", "",
                 "Latence capteur → alarme : bornée et prouvée."]
    else:
        corps = lignes_utiles(scene["source"])
    y = 130
    for l in corps:
        if l == "":
            y += 22
            continue
        f = taille_fonctionnelle(d, l, FONTS["corps"], LARGEUR - 90)
        d.text((45, y), l, font=f, fill=COULEUR_CODE)
        y += f.size + 8
        if y > HAUTEUR - 150:
            d.text((45, y), "…", font=f_sous, fill=COULEUR_TEXTE)
            break
    # Sous-titre (voix-off) en bas, sur bande, coupé sur plusieurs lignes
    f_narr = ImageFont.truetype(FONTS["sous"], 24)
    narration_lignes = envelopper(d, scene["narration"], f_narr, LARGEUR - 90)
    hauteur_bande = 20 + 30 * len(narration_lignes)
    y_bande = HAUTEUR - hauteur_bande
    d.rectangle((0, y_bande, LARGEUR, HAUTEUR), fill=(10, 16, 24))
    for k, l in enumerate(narration_lignes):
        d.text((45, y_bande + 14 + 30 * k), l, font=f_narr, fill=COULEUR_SOUS_TITRE)
    # Source de la capture, en petit
    if scene["source"] != "-":
        f_min = ImageFont.truetype(FONTS["sous"], 16)
        d.text((LARGEUR - 360, 8), scene["source"], font=f_min, fill=(120, 140, 160))
    nom = os.path.join(DOSSIER_PLANS, f"plan-{index:02d}.png")
    img.save(nom)
    return nom


def table_markdown(scenes):
    """Storyboard Markdown (colonne temps cumulé)."""
    lignes = ["| # | Début | Fin | Image | Texte / voix-off | Prouve |",
              "|---|---|---|---|---|---|"]
    t = 0.0
    for i, s in enumerate(scenes, 1):
        debut = f"{int(t//60)}:{int(t%60):02d}"
        fin_t = t + s["duree"]
        fin = f"{int(fin_t//60)}:{int(fin_t%60):02d}"
        source = s["source"] if s["source"] != "-" else "texte"
        lignes.append(f"| {i} | {debut} | {fin} | {source} | {s['narration']} | {s['titre']} |")
        t = fin_t
    return "\n".join(lignes)


def main():
    if "--table" in sys.argv:
        print(table_markdown(charger_scenes(os.path.join(RACINE, "scenes.tsv"))))
        return
    scenes = charger_scenes(os.path.join(RACINE, "scenes.tsv"))
    if "--liste" in sys.argv:
        for i, s in enumerate(scenes, 1):
            print(f"{i}\t{s['duree']}s\t{s['titre']}\t{s['source']}")
        return
    os.makedirs(DOSSIER_PLANS, exist_ok=True)
    for i, s in enumerate(scenes, 1):
        nom = dessiner_scene(s, i)
        print(f"[plan {i:02d}] {s['duree']:>4}s  {s['titre']:<34} -> {nom}")


if __name__ == "__main__":
    main()