#!/usr/bin/env bash
# montage.sh — assemble les captures Veille en une vidéo MP4 (< 3 min).
#
# 1. Vérifie la présence de ffmpeg (sinon message clair et arrêt).
# 2. Régénère les plans PNG à partir de `scenes.tsv` (via rendu.py, Pillow requis).
# 3. Assemble les plans (durées de scenes.tsv) + une piste audio (silence, ou
#    une voix-off `preuve/video/voix-off.{wav,mp3}` si présente) → `veille.mp4`.
#
# Usage :
#   bash preuve/video/captures.sh   # d'abord : produire les captures réelles
#   bash preuve/video/montage.sh    # assembler la vidéo
#
# Variables d'environnement :
#   SORTIE     chemin de sortie (défaut : preuve/video/veille.mp4)

set -euo pipefail

RACINE="$(cd "$(dirname "$0")/../.." && pwd)"
DOSSIER="$(cd "$(dirname "$0")" && pwd)"
SORTIE="${SORTIE:-$DOSSIER/veille.mp4}"

echo "== montage Veille =="

if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "ERREUR : ffmpeg est introuvable." >&2
  echo "        Installe-le (ex. 'apt install ffmpeg'), puis relance montage.sh." >&2
  exit 2
fi

# Plans : les (re)générer via rendu.py (Pillow requis).
python3 "$DOSSIER/rendu.py" > /dev/null || {
  echo "ERREUR : génération des plans impossible (Pillow absent ?)." >&2
  echo "        Les plans doivent exister dans $DOSSIER/plans/ avant le montage." >&2
  exit 2
}

# Liste de concat (une image + sa durée, dernière image répétée).
# Le décodeur concat duplique la durée de la dernière image : on borne la
# vidéo à la durée totale des plans, calculée depuis scenes.tsv.
LISTE="$(mktemp)"
TOTAL="$(python3 "$DOSSIER/rendu.py" --liste | awk -F'\t' '{s+=$2} END {printf "%d", s}')"
python3 "$DOSSIER/rendu.py" --liste | while IFS=$'\t' read -r num duree titre source; do
  printf "file '%s/plans/plan-%02d.png'\nduration %s\n" "$DOSSIER" "$num" "$duree"
done > "$LISTE"
dernier="$(python3 "$DOSSIER/rendu.py" --liste | tail -1 | cut -f1)"
printf "file '%s/plans/plan-%02d.png'\n" "$DOSSIER" "$dernier" >> "$LISTE"
echo "durée planifiée : ${TOTAL}s"

# Piste audio : voix-off si présente, sinon un silence (piste dub-able).
AUDIO=()
if [ -f "$DOSSIER/voix-off.wav" ]; then
  echo "voix-off détectée : voix-off.wav"
  AUDIO=(-i "$DOSSIER/voix-off.wav")
elif [ -f "$DOSSIER/voix-off.mp3" ]; then
  echo "voix-off détectée : voix-off.mp3"
  AUDIO=(-i "$DOSSIER/voix-off.mp3")
else
  echo "aucune voix-off : piste audio silencieuse (les sous-titres portent la narration)."
  AUDIO=(-f lavfi -i anullsrc=r=44100:cl=stereo -shortest)
fi

# Assemblage : H.264 1280x720, 30 i/s, audio AAC.
ffmpeg -hide_banner -loglevel error -y -f concat -safe 0 -i "$LISTE" \
  "${AUDIO[@]}" \
  -c:v libx264 -preset medium -crf 20 -r 30 -pix_fmt yuv420p \
  -c:a aac -b:a 128k -t "$TOTAL" -movflags +faststart \
  "$SORTIE"

rm -f "$LISTE"

du -h "$SORTIE"
DURATION="$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$SORTIE" 2>/dev/null || echo '?')"
echo "durée : ${DURATION}s"
if [ "$(echo "$DURATION >= 180" | bc 2>/dev/null || echo 0)" = "1" ]; then
  echo "ATTENTION : la vidéo dépasse 3 minutes." >&2
  exit 3
fi
echo "[OK] vidéo assemblée : $SORTIE"