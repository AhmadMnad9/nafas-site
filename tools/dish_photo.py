#!/usr/bin/env python3
"""Retouch a dish photo for the Nafas gallery, the way a food photographer edits a shot.

Light, colour, a close 4:3 crop on the dish, a soft background and a little sharpening.
The food itself is never redrawn: every change is a tone or colour change over the whole
frame, or blur outside the dish, so the plate still shows what the cook really made.

usage
  python3 tools/dish_photo.py PHOTO --slug yalanji-umm-khaled [options]

options (all optional; the defaults suit most phone photos)
  --focus CX,CY,RX,RY  the dish region as fractions of the photo: centre x, centre y,
                       half-width, half-height. Without it the dish is guessed from colour
                       and texture, so always look at the result.
  --shape ellipse|rect ellipse for a plate or a bowl, rect for a tray (default ellipse)
  --tight 1.04         crop size against the dish: 1 = the dish edge touches the frame,
                       below 1 crops into the dish (closer), above 1 leaves table around it
  --blur 0.45          background softness, 0..1 (overhead trays 0.15-0.3, angled plates 0.5-0.8)
  --warmth 3           added warmth (b* units); food reads better a little warm
  --wb 0.7             how much of a colour cast to remove, 0..1
  --exposure 0         brightness of the dish, -1..1 around a well-lit default
  --contrast 1         S-curve strength, 0..2
  --shadows 0.2        lift for dark food (leaves, meat, burnt cheese), 0..0.8
  --vibrance 0.18      boost for dull colours, 0..0.6
  --clarity 0.3        local contrast (texture), 0..1
  --vignette 0.16      darker edges, 0..0.5
  --width 2000         longest output side in pixels (smaller photos are upscaled 2x first)

writes
  src/photos/<slug>.jpg         the edited photo (the build makes the WebP sizes)
  src/photos/<slug>.edit.json   the settings used, to redo or tweak the edit
  originals/<slug>.<ext>        the untouched original
  work/<slug>-compare.jpg       before and after side by side, to send for approval
"""
import argparse
import json
import shutil
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps

ROOT = Path(__file__).resolve().parent.parent
MODEL = ROOT / "tools" / "models" / "FSRCNN_x2.pb"
PAPER = (251, 248, 245)
CORAL = (225, 52, 30)


# ---------- helpers
def smoothstep(x):
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3 - 2 * x)


def norm01(x):
    lo, hi = np.percentile(x, 1), np.percentile(x, 99)
    return np.clip((x - lo) / max(hi - lo, 1e-6), 0, 1)


def load_rgb(path):
    im = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
    return np.asarray(im).astype(np.float32) / 255.0


def lab_of(rgb):
    return cv2.cvtColor(rgb.astype(np.float32), cv2.COLOR_RGB2LAB)  # float: L 0..100, a/b about -127..127


def rgb_of(lab):
    return np.clip(cv2.cvtColor(lab.astype(np.float32), cv2.COLOR_LAB2RGB), 0, 1)


# ---------- where the dish is
def auto_focus(rgb):
    """Guess the dish: colourful, textured and near the middle. A fallback only."""
    h, w = rgb.shape[:2]
    s = 360 / max(h, w)
    small = cv2.resize(rgb, (max(1, int(w * s)), max(1, int(h * s))), interpolation=cv2.INTER_AREA)
    sh, sw = small.shape[:2]
    lab = lab_of(small)
    chroma = np.sqrt(lab[..., 1] ** 2 + lab[..., 2] ** 2)
    tex = cv2.GaussianBlur(np.abs(cv2.Laplacian(lab[..., 0], cv2.CV_32F, ksize=3)), (0, 0), 4)
    e = max(4, int(0.06 * min(sh, sw)))                     # the frame edge is mostly table
    edge = np.concatenate([lab[:e].reshape(-1, 3), lab[-e:].reshape(-1, 3),
                           lab[:, :e].reshape(-1, 3), lab[:, -e:].reshape(-1, 3)])
    table = np.median(edge, axis=0)
    differs = np.sqrt(((lab - table) * np.array([0.5, 1.0, 1.0], np.float32)) ** 2).sum(axis=2)
    score = 0.55 * norm01(differs) + 0.25 * norm01(tex) + 0.20 * norm01(chroma)
    yy, xx = np.mgrid[0:sh, 0:sw].astype(np.float32)
    prior = np.exp(-(((xx - sw / 2) / (0.45 * sw)) ** 2 + ((yy - sh / 2) / (0.45 * sh)) ** 2))
    score = cv2.GaussianBlur(score * (0.5 + 0.5 * prior), (0, 0), 6)
    mask = (score > np.percentile(score, 55)).astype(np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
    n, _, stats, _ = cv2.connectedComponentsWithStats(mask)
    if n < 2:
        return (0.5, 0.5, 0.35, 0.35)
    i = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    x, y, bw, bh = stats[i, :4]
    return (float((x + bw / 2) / sw), float((y + bh / 2) / sh), float(bw / 2 / sw * 1.05), float(bh / 2 / sh * 1.05))


def crop_box(W, H, focus, tight, aspect=4 / 3):
    cx, cy, rx, ry = focus[0] * W, focus[1] * H, focus[2] * W, focus[3] * H
    bw, bh = 2 * rx * tight, 2 * ry * tight
    if bw / bh < aspect:
        bw = bh * aspect
    else:
        bh = bw / aspect
    s = min(1.0, W / bw, H / bh)          # never larger than the photo
    bw, bh = bw * s, bh * s
    x0 = min(max(cx - bw / 2, 0), W - bw)
    y0 = min(max(cy - bh / 2, 0), H - bh)
    return int(round(x0)), int(round(y0)), int(round(bw)), int(round(bh))


def dish_mask(h, w, f, shape, feather=0.22):
    """1 on the dish, fading to 0 outside it. f = (cx, cy, rx, ry) in pixels."""
    cx, cy, rx, ry = (float(v) for v in f)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    n = 2.0 if shape == "ellipse" else 6.0
    d = (np.abs((xx - cx) / max(rx, 1)) ** n + np.abs((yy - cy) / max(ry, 1)) ** n) ** (1 / n)
    return smoothstep((1 + feather - d) / feather).astype(np.float32)


# ---------- the edit
def denoise(rgb8):
    return cv2.fastNlMeansDenoisingColored(rgb8, None, 3, 3, 7, 21)


def upscale2x(rgb8):
    if MODEL.exists() and hasattr(cv2, "dnn_superres"):
        sr = cv2.dnn_superres.DnnSuperResImpl_create()
        sr.readModel(str(MODEL))
        sr.setModel("fsrcnn", 2)
        bgr = sr.upsample(cv2.cvtColor(rgb8, cv2.COLOR_RGB2BGR))
        return cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB), "fsrcnn"
    h, w = rgb8.shape[:2]
    return cv2.resize(rgb8, (w * 2, h * 2), interpolation=cv2.INTER_LANCZOS4), "lanczos"


def white_balance(lab, strength, warmth):
    L, a, b = cv2.split(lab)
    chroma = np.sqrt(a * a + b * b)
    neutral = (chroma < 14) & (L > 30) & (L < 96)
    if neutral.mean() > 0.015:                      # plates, cloths, metal: real neutrals
        da, db, src = float(a[neutral].mean()), float(b[neutral].mean()), "neutrals"
    else:                                           # none in shot: a weak grey-world guess
        da, db, src = float(np.median(a)) * 0.3, float(np.median(b)) * 0.3, "grey-world"
    da, db = float(np.clip(da, -10, 10)), float(np.clip(db, -10, 10))
    a = a - strength * da + warmth * 0.2
    b = b - strength * db + warmth
    return cv2.merge([L, a, b]), {"cast_a": round(da, 2), "cast_b": round(db, 2), "from": src}


def tone(l, m, exposure, contrast, shadows):
    """l: lightness 0..1. Exposure is judged on the dish (mask m), not the room."""
    lo, hi = float(np.percentile(l, 0.3)), float(np.percentile(l, 99.8))
    new_lo = lo * 0.5 if lo > 0.03 else lo                   # lift the haze, half way
    new_hi = hi + (0.97 - hi) * 0.6 if hi < 0.95 else hi     # open dull highlights, without clipping
    l = np.clip(new_lo + (l - lo) * (new_hi - new_lo) / max(hi - lo, 1e-3), 0, 1)
    weights = m > 0.5
    med = float(np.median(l[weights])) if weights.mean() > 0.05 else float(np.median(l))
    target = float(np.clip(np.clip(med, 0.42, 0.60) + 0.08 * exposure, 0.3, 0.75))
    g = float(np.clip(np.log(target) / np.log(np.clip(med, 0.05, 0.95)), 0.7, 1.4))
    l = l ** g
    if shadows > 0:                                          # open dark food (leaves, meat) a little
        w = 1 - smoothstep(l / 0.55)
        l = l * (1 - w) + (l ** (1 / (1 + shadows))) * w
    k = 0.18 * contrast
    l = l - k * np.sin(2 * np.pi * l) / (2 * np.pi)   # S-curve, ends fixed
    return np.clip(l, 0, 1).astype(np.float32), {"black": round(float(lo), 3), "white": round(float(hi), 3),
                              "dish_median_before": round(med, 3), "gamma": round(g, 3)}


def vibrance(a, b, v):
    c = np.sqrt(a * a + b * b)
    gain = 1 + v * np.clip(1 - c / 85.0, 0, 1)
    return a * gain, b * gain


def retouch(rgb, mask, o):
    lab = lab_of(rgb)
    lab, wb = white_balance(lab, o.wb, o.warmth)
    L, a, b = cv2.split(lab)
    l, tn = tone(L / 100.0, mask, o.exposure, o.contrast, o.shadows)
    if o.clarity > 0:                               # texture: large-radius unsharp on lightness
        sigma = 0.012 * max(l.shape)
        l = np.clip(l + o.clarity * 0.8 * (l - cv2.GaussianBlur(l, (0, 0), sigma)), 0, 1)
    rich = max(0.0, (1 / max(tn["gamma"], 0.5) - 1) * 0.5)
    a, b = vibrance(a, b, o.vibrance + rich)
    out = rgb_of(cv2.merge([l * 100.0, a, b]))
    h, w = out.shape[:2]
    if o.blur > 0:                                  # soft background, like a wide aperture
        soft = cv2.GaussianBlur(out, (0, 0), o.blur * 0.011 * max(h, w))
        m3 = mask[..., None]
        out = out * m3 + soft * (1 - m3)
        out = out * (1 - 0.10 * o.blur * (1 - m3))
    if o.vignette > 0:
        yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
        r = np.sqrt(((xx - w / 2) / (w / 2)) ** 2 + ((yy - h / 2) / (h / 2)) ** 2) / np.sqrt(2)
        out = out * (1 - o.vignette * smoothstep((r - 0.45) / 0.55))[..., None]
    return np.clip(out, 0, 1).astype(np.float32), {"white_balance": wb, "tone": tn}


def sharpen(rgb, amount=0.55, sigma=1.0):
    lab = lab_of(rgb.astype(np.float32))
    L = lab[..., 0]
    lab[..., 0] = np.clip(L + amount * (L - cv2.GaussianBlur(L, (0, 0), sigma)), 0, 100)
    return rgb_of(lab)


# ---------- before / after sheet
def label_font(size):
    ttf = ROOT / "work" / "cairo-label.ttf"
    if not ttf.exists():
        try:
            from fontTools.ttLib import TTFont
            ttf.parent.mkdir(parents=True, exist_ok=True)
            f = TTFont(str(ROOT / "src" / "fonts" / "cairo.woff2"))
            f.flavor = None
            f.save(str(ttf))
        except Exception:
            ttf = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
    try:
        font = ImageFont.truetype(str(ttf), size)
        try:
            font.set_variation_by_axes([700])
        except Exception:
            pass
        return font
    except Exception:
        return ImageFont.load_default()


def compare_sheet(orig, box, result, path):
    """Before on the right and after on the left, the way Arabic reads."""
    cell_w, cell_h, pad, top = 900, 675, 24, 64
    sheet = Image.new("RGB", (cell_w * 2 + pad * 3, cell_h + top + pad), PAPER)
    draw = ImageDraw.Draw(sheet)
    o = Image.fromarray((orig * 255).astype(np.uint8))
    s = min(cell_w / o.width, cell_h / o.height)
    o = o.resize((int(o.width * s), int(o.height * s)), Image.LANCZOS)
    ox = pad * 2 + cell_w + (cell_w - o.width) // 2
    oy = top + (cell_h - o.height) // 2
    sheet.paste(o, (ox, oy))
    x0, y0, bw, bh = box
    draw.rectangle([ox + x0 * s, oy + y0 * s, ox + (x0 + bw) * s, oy + (y0 + bh) * s], outline=CORAL, width=3)
    r = Image.fromarray((result * 255).astype(np.uint8))
    s2 = min(cell_w / r.width, cell_h / r.height)
    r = r.resize((int(r.width * s2), int(r.height * s2)), Image.LANCZOS)
    sheet.paste(r, (pad + (cell_w - r.width) // 2, top + (cell_h - r.height) // 2))
    font = label_font(30)
    for text, cx in (("قبل", pad * 2 + cell_w + cell_w // 2), ("بعد", pad + cell_w // 2)):
        try:
            draw.text((cx, top // 2), text, font=font, fill=(53, 5, 2), anchor="mm", direction="rtl")
        except Exception:
            draw.text((cx, top // 2), text, font=font, fill=(53, 5, 2), anchor="mm")
    sheet.save(path, quality=88)


# ---------- main
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("photo")
    ap.add_argument("--slug", required=True)
    ap.add_argument("--focus")
    ap.add_argument("--shape", choices=["ellipse", "rect"], default="ellipse")
    ap.add_argument("--tight", type=float, default=1.04)
    ap.add_argument("--blur", type=float, default=0.45)
    ap.add_argument("--warmth", type=float, default=3.0)
    ap.add_argument("--wb", type=float, default=0.7)
    ap.add_argument("--exposure", type=float, default=0.0)
    ap.add_argument("--contrast", type=float, default=1.0)
    ap.add_argument("--shadows", type=float, default=0.2)
    ap.add_argument("--vibrance", type=float, default=0.18)
    ap.add_argument("--clarity", type=float, default=0.3)
    ap.add_argument("--vignette", type=float, default=0.16)
    ap.add_argument("--width", type=int, default=2000)
    o = ap.parse_args()

    src = Path(o.photo)
    rgb = load_rgb(src)
    H, W = rgb.shape[:2]
    focus = tuple(float(v) for v in o.focus.split(",")) if o.focus else auto_focus(rgb)
    x0, y0, bw, bh = crop_box(W, H, focus, o.tight)
    crop = rgb[y0:y0 + bh, x0:x0 + bw]

    # small crops: clean the noise, then upscale 2x so the gallery stays sharp
    crop8 = (crop * 255).astype(np.uint8)
    upscaled = None
    if crop8.shape[1] < 1100:
        crop8 = denoise(crop8)
        crop8, upscaled = upscale2x(crop8)
    work = crop8.astype(np.float32) / 255.0
    if max(work.shape[:2]) > 2400:                    # keep the maths quick
        s = 2400 / max(work.shape[:2])
        work = cv2.resize(work, (int(work.shape[1] * s), int(work.shape[0] * s)), interpolation=cv2.INTER_AREA)
    h, w = work.shape[:2]
    sx, sy = w / bw, h / bh
    fpx = ((focus[0] * W - x0) * sx, (focus[1] * H - y0) * sy, focus[2] * W * sx * 1.06, focus[3] * H * sy * 1.06)
    mask = dish_mask(h, w, fpx, o.shape, feather=0.28)

    out, stats = retouch(work, mask, o)
    longest = max(out.shape[:2])
    if longest > o.width:
        s = o.width / longest
        out = cv2.resize(out, (int(out.shape[1] * s), int(out.shape[0] * s)), interpolation=cv2.INTER_AREA)
    out = sharpen(out)

    photos = ROOT / "src" / "photos"
    photos.mkdir(parents=True, exist_ok=True)
    (ROOT / "originals").mkdir(exist_ok=True)
    (ROOT / "work").mkdir(exist_ok=True)
    out_path = photos / f"{o.slug}.jpg"
    Image.fromarray((out * 255).astype(np.uint8)).save(out_path, quality=92, optimize=True, progressive=True)
    keep = ROOT / "originals" / f"{o.slug}{src.suffix.lower() or '.jpg'}"
    if src.resolve() != keep.resolve():
        shutil.copyfile(src, keep)
    compare = ROOT / "work" / f"{o.slug}-compare.jpg"
    compare_sheet(rgb, (x0, y0, bw, bh), out, compare)

    settings = {k: getattr(o, k) for k in ("shape", "tight", "blur", "warmth", "wb", "exposure",
                                          "contrast", "shadows", "vibrance", "clarity", "vignette", "width")}
    record = {
        "source": keep.name, "source_size": [W, H],
        "focus": [round(v, 4) for v in focus], "focus_from": "given" if o.focus else "auto",
        "crop": [x0, y0, bw, bh], "upscaled": upscaled,
        "output": out_path.name, "output_size": [out.shape[1], out.shape[0]],
        "settings": settings, "measured": stats,
    }
    (photos / f"{o.slug}.edit.json").write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"photo": str(out_path.relative_to(ROOT)), "compare": str(compare.relative_to(ROOT)),
                      "focus": record["focus"], "focus_from": record["focus_from"], "crop": record["crop"],
                      "upscaled": upscaled, "size": record["output_size"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
