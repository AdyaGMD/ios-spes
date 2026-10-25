#!/bin/bash
# From joranv1/ios-sailfish tools/wallpaper-heic2png.sh (same ios-sweet lineage). spes (iPhone X
# userland) has no HEVC decoder either: PosterBoard showed no posters at all.
# wallpaper-heic2png.sh ROOT: make the stock layered wallpapers drawable on the
# Pixel. Their layers (/Library/Wallpaper/Collections/*/Wallpapers/*.wallpaper/
# *.ca/assets/*.HEIC) need the A11's hardware HEVC decoder, which the phone
# lacks: only the background gradient showed (iOS 16 "WWDC 2022" = plain blue).
# Each HEIC gets a lossless PNG twin (sips, alpha kept) and the layer's
# main.caml points at it. The HEIC files stay. Run on a mounted root (macOS).
set -euo pipefail
root=$1
n=0
while IFS= read -r -d '' heic; do
	png=${heic%.*}.png
	[[ -e $png ]] || sips -s format png "$heic" --out "$png" >/dev/null
	n=$((n + 1))
done < <(find "$root/Library/Wallpaper/Collections" -name '*.HEIC' -print0)
while IFS= read -r -d '' caml; do
	grep -q '\.HEIC"' "$caml" || continue
	sed -i '' 's/\.HEIC"/.png"/g' "$caml"
	if grep -q '\.HEIC"' "$caml"; then echo "still HEIC in $caml" >&2; exit 1; fi
	echo "edited ${caml#"$root"/}"
done < <(find "$root/Library/Wallpaper/Collections" -name main.caml -print0)
echo "$n HEIC images converted"
