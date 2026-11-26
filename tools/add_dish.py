#!/usr/bin/env python3
"""Put an edited dish photo into the homepage gallery «من مطبخ الشام».

Run tools/dish_photo.py first; it leaves the photo at src/photos/<slug>.jpg.

usage
  python3 tools/add_dish.py --slug SLUG --name "اسم الطبق" --desc "وصف قصير" \
      [--cook "اسم المطبخ"] [--alt "وصف الصورة"] [--replace OLD_SLUG] [--ai] [--dry-run]

Where the card goes
  --replace OLD_SLUG   takes that card's place.
  same dish name       a card with the same name is replaced in place.
  otherwise            the new card goes first. If that makes more cards than "max" in
                       src/dishes.json, the last stand-in (illustrative) card drops out.
                       When every card is a real photo, the script stops and asks for --replace.
--cook is only for dishes from a Nafas cook: the card then says «من مطبخ …», and the About
page says which photos come from our cooks' kitchens.
--ai marks a photo whose camera angle was changed with AI from a real photo of the same dish.
The About page then says so, and the homepage promise about photos is worded to stay true.
"""
import argparse
import json
from pathlib import Path

from PIL import Image, ImageOps, ImageStat

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def save(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def placeholder_colour(photo):
    """The colour shown while the photo loads: its average, darkened a little."""
    im = ImageOps.exif_transpose(Image.open(photo)).convert("RGB").resize((32, 24))
    r, g, b = (int(c * 0.8) for c in ImageStat.Stat(im).mean)
    return f"#{r:02x}{g:02x}{b:02x}"


def used_elsewhere(slug, dishes):
    if any(d["slug"] == slug for d in dishes["dishes"]):
        return True
    return any(slug in p.read_text(encoding="utf-8") for p in (SRC / "pages").glob("*.html"))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--slug", required=True)
    ap.add_argument("--name", required=True)
    ap.add_argument("--desc", required=True)
    ap.add_argument("--cook")
    ap.add_argument("--alt")
    ap.add_argument("--replace")
    ap.add_argument("--ai", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    o = ap.parse_args()

    photo = SRC / "photos" / f"{o.slug}.jpg"
    if not photo.exists():
        raise SystemExit(f"no photo at {photo.relative_to(ROOT)}: run tools/dish_photo.py first")

    photos = load(SRC / "photos.json")
    dishes = load(SRC / "dishes.json")
    cards = dishes["dishes"]
    limit = dishes.get("max", 6)

    with Image.open(photo) as im:
        w, h = ImageOps.exif_transpose(im).size
    alt = o.alt or f"{o.name}: {o.desc}"
    photos[o.slug] = {"source": "own", "w": w, "h": h, "color": placeholder_colour(photo),
                      "alt": alt, "caption": "", "credit": ""}

    card = {"slug": o.slug, "name": o.name.strip(), "desc": o.desc.strip(), "kind": "real"}
    if o.cook:
        card["cook"] = o.cook.strip()
    if o.ai:
        card["ai"] = True
        photos[o.slug]["ai"] = True

    removed = []
    target = None
    if o.replace:
        target = next((i for i, d in enumerate(cards) if d["slug"] == o.replace), None)
        if target is None:
            raise SystemExit(f"--replace {o.replace}: no such card in src/dishes.json")
    else:
        target = next((i for i, d in enumerate(cards) if d["name"] == card["name"]), None)

    if target is not None:
        removed.append(cards[target]["slug"])
        cards[target] = card
        action = f"replaced «{removed[0]}»"
    else:
        cards.insert(0, card)
        action = "added first"
        while len(cards) > limit:
            stand_in = next((i for i in range(len(cards) - 1, -1, -1) if cards[i]["kind"] == "illustrative"), None)
            if stand_in is None:
                raise SystemExit("every card is already a real photo: pick one to swap out with --replace SLUG\n"
                                 + "\n".join(f"  {d['slug']}: {d['name']}" for d in cards[1:]))
            removed.append(cards.pop(stand_in)["slug"])

    # a photo nothing shows any more leaves photos.json (its file stays, in case it comes back)
    retired = [s for s in removed if s != o.slug and not used_elsewhere(s, dishes)]
    for s in retired:
        photos.pop(s, None)

    if not o.dry_run:
        save(SRC / "photos.json", photos)
        save(SRC / "dishes.json", dishes)
    print(json.dumps({"action": action, "card": card, "dropped_cards": removed, "retired_photos": retired,
                      "gallery": [f"{d['name']} ({d['kind']})" for d in cards], "dry_run": o.dry_run},
                     ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
