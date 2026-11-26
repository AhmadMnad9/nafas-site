#!/usr/bin/env python3
"""Build the نَفَس website: src/ -> dist/.

Photos: if src/photos/<slug>.(jpg|jpeg|png|webp) exists, it is resized into WebP variants
and served from the site itself. Otherwise the photo is hot-linked from Unsplash's CDN
(the method Unsplash asks API users to follow), with responsive widths.

usage: python3 tools/build.py [--site-url https://example.netlify.app/]
(or put the address in src/site-url.txt once, and every build uses it)
"""
import json, re, shutil, base64, io, hashlib, sys, html, os
from pathlib import Path
from PIL import Image
import blurhash

ROOT = Path(__file__).resolve().parent.parent
SRC, DIST = ROOT / "src", ROOT / "dist"
WA_DIGITS = "963962934928"
WA_PRETTY = "+963 962 934 928"
WIDTHS = [480, 800, 1200, 1600, 2000]
UTM = "utm_source=nafas&utm_medium=referral"

args = sys.argv[1:]
SITE_URL = args[args.index("--site-url") + 1] if "--site-url" in args else ""
if not SITE_URL and (SRC / "site-url.txt").exists():      # set once the site has its address
    SITE_URL = (SRC / "site-url.txt").read_text(encoding="utf-8").strip()
if SITE_URL and not SITE_URL.endswith("/"): SITE_URL += "/"

photos = json.loads((SRC / "photos.json").read_text(encoding="utf-8"))
DISHES = json.loads((SRC / "dishes.json").read_text(encoding="utf-8"))
wordmark = (SRC / "brand" / "wordmark-inline.svg").read_text(encoding="utf-8")
ICONS = {
  "wa": '<svg viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M12 2a10 10 0 0 0-8.6 15.1L2 22l5-1.3A10 10 0 1 0 12 2Zm0 18.2a8.2 8.2 0 0 1-4.2-1.2l-.3-.2-3 .8.8-2.9-.2-.3A8.2 8.2 0 1 1 12 20.2Zm4.5-6.1c-.2-.1-1.5-.7-1.7-.8s-.4-.1-.6.1-.7.8-.8 1-.3.2-.5.1a6.7 6.7 0 0 1-3.3-2.9c-.2-.4.2-.4.7-1.3a.5.5 0 0 0 0-.5l-.8-1.9c-.2-.5-.4-.4-.6-.4h-.5a1 1 0 0 0-.7.3 3 3 0 0 0-.9 2.2 5.2 5.2 0 0 0 1.1 2.7 11.8 11.8 0 0 0 4.5 4c1.7.7 2.3.8 3.2.6a2.7 2.7 0 0 0 1.8-1.3 2.2 2.2 0 0 0 .1-1.3c0-.1-.2-.2-.5-.3Z"/></svg>',
  "check": '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="10.2" fill="none" stroke="currentColor" stroke-width="1.6"/><path d="m7.6 12.4 3 3 5.8-6.2" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  "home": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 11.5 12 5l8 6.5V20a1 1 0 0 1-1 1h-4.5v-5.5h-5V21H5a1 1 0 0 1-1-1z" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/></svg>',
  "eye": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12Z" fill="none" stroke="currentColor" stroke-width="1.6"/><circle cx="12" cy="12" r="3" fill="none" stroke="currentColor" stroke-width="1.6"/></svg>',
  "lock": '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="5" y="10.5" width="14" height="10" rx="2" fill="none" stroke="currentColor" stroke-width="1.6"/><path d="M8.5 10.5V8a3.5 3.5 0 0 1 7 0v2.5" fill="none" stroke="currentColor" stroke-width="1.6"/></svg>',
}

# ---------------------------------------------------------------- photos
def lqip_from_blurhash(bh, w, h):
    sw = 20; sh = max(6, round(20 * h / w))
    im = blurhash.decode(bh, sw, sh).convert("RGB")
    b = io.BytesIO(); im.save(b, "WEBP", quality=60)
    return "data:image/webp;base64," + base64.b64encode(b.getvalue()).decode()

def find_local(slug):
    for ext in ("jpg", "jpeg", "png", "webp", "JPG", "JPEG", "PNG"):
        p = SRC / "photos" / f"{slug}.{ext}"
        if p.exists(): return p
    return None

PHOTO = {}
def prepare_photos():
    outdir = DIST / "assets" / "img"; outdir.mkdir(parents=True, exist_ok=True)
    for slug, m in photos.items():
        local = find_local(slug)
        info = dict(m)
        if local:
            im = Image.open(local); im = im.convert("RGB")
            # respect EXIF orientation
            try:
                from PIL import ImageOps; im = ImageOps.exif_transpose(im)
            except Exception: pass
            W, H = im.size
            crop = m.get("crop")  # optional [x0,y0,x1,y1] fractions
            if crop:
                im = im.crop((int(crop[0]*W), int(crop[1]*H), int(crop[2]*W), int(crop[3]*H))); W, H = im.size
            srcset = []
            for w in [x for x in WIDTHS if x < W] + [min(W, 2400)]:
                if any(s[1] == w for s in srcset): continue
                h = round(H * w / W)
                fn = f"{slug}-{w}.webp"
                im.resize((w, h), Image.LANCZOS).save(outdir / fn, "WEBP", quality=74, method=6)
                srcset.append((f"assets/img/{fn}", w))
            tiny = im.resize((20, max(6, round(20 * H / W))), Image.BILINEAR)
            b = io.BytesIO(); tiny.save(b, "WEBP", quality=55)
            info.update(mode="local", W=W, H=H, srcset=srcset,
                        lqip="data:image/webp;base64," + base64.b64encode(b.getvalue()).decode())
        else:
            if m.get("source") == "own":
                raise SystemExit(f"missing local file for own photo: src/photos/{slug}.jpg")
            W, H = m["w"], m["h"]
            srcset = [(f'{m["raw"]}&w={w}&q=70&auto=format&fit=max', w) for w in WIDTHS]
            info.update(mode="remote", W=W, H=H, srcset=srcset, lqip=lqip_from_blurhash(m["blurhash"], W, H))
        PHOTO[slug] = info
    return PHOTO

def credit_html(slug, prefix="تصوير "):
    m = PHOTO[slug]
    if m.get("source") == "own":
        return ""
    return (f'{prefix}<a href="https://unsplash.com/@{m["user"]}?{UTM}" rel="noopener">{html.escape(m["credit"])}</a>'
            f' على <a href="https://unsplash.com/?{UTM}" rel="noopener">Unsplash</a>')

def img_html(slug, sizes="100vw", eager=False, pos=None, cls="", alt=None):
    m = PHOTO[slug]
    srcset = ", ".join(f"{u} {w}w" for u, w in m["srcset"])
    src = m["srcset"][min(1, len(m["srcset"]) - 1)][0]
    W, H = m["W"], m["H"]
    style = f' style="object-position:{pos}"' if pos else ""
    load = 'loading="eager" fetchpriority="high"' if eager else 'loading="lazy"'
    a = html.escape(alt if alt is not None else m["alt"])
    extra = ' referrerpolicy="no-referrer-when-downgrade"' if m["mode"] == "remote" else ""
    return (f'<span class="ph {cls}" style="--ph:url({m["lqip"]});--phc:{m["color"]}">'
            f'<img src="{src}" srcset="{srcset}" sizes="{sizes}" width="{W}" height="{H}" alt="{a}" {load} decoding="async"{style}{extra}></span>')

def fig_html(slug, ratio="4x3", sizes="100vw", caption=None, pos=None, cls="", eager=False, credit=True):
    m = PHOTO[slug]
    cap = caption if caption is not None else m["caption"]
    capb = f"<b>{html.escape(cap)}</b>" if cap else ""
    c = credit_html(slug) if credit else ""
    cr = f'<span class="credit">{c}</span>' if c else ""
    cap_html = f'<figcaption>{capb}{cr}</figcaption>' if (capb or cr) else ""
    return f'<figure class="fig r-{ratio} {cls}">{img_html(slug, sizes, eager, pos)}{cap_html}</figure>'

# ---------------------------------------------------------------- homepage gallery
def dishes_markup():
    """The «من مطبخ الشام» cards, from src/dishes.json (edited by tools/add_dish.py)."""
    items = []
    for d in DISHES["dishes"][: DISHES.get("max", 6)]:
        if d["slug"] not in photos:
            raise SystemExit(f"dishes.json: no photo entry for {d['slug']} in photos.json")
        cook = f'<p class="dish-cook">من مطبخ {html.escape(d["cook"])}</p>' if d.get("cook") else ""
        items.append(f'      <li class="dish-card">{{{{img {d["slug"]} sizes="{DISHES.get("sizes", "50vw")}"}}}}'
                     f'<h3>{html.escape(d["name"])}</h3><p>{html.escape(d["desc"])}</p>{cook}</li>')
    return '<ul class="dishes">\n' + "\n".join(items) + "\n    </ul>"

def about_photos_note(remote_slugs):
    """Keep the About page's sentence about photos true to what the site shows."""
    from_cooks = any(d.get("cook") for d in DISHES["dishes"])
    first = ("صور الأطباق يلي تحتها اسم مطبخ هي من مطابخ طاهياتنا، ومعدّلة بالإضاءة والألوان بس. وباقي الصور للتوضيح."
             if from_cooks else "الصور بالموقع للتوضيح، ومو من مطابخ طاهياتنا.")
    unsplash = ("وصورة السوق من Unsplash، واسم مصوّرها تحت." if remote_slugs == ["damascus-souq"]
                else "والصور يلي من Unsplash، أسماء مصوّريها تحت." if remote_slugs else "")
    last = "" if from_cooks else "صور طاهياتنا وأطباقهن الحقيقية رح تنزل لما نبلّش."
    return " ".join(x for x in (first, unsplash, last) if x)

# ---------------------------------------------------------------- templating
ATTR = re.compile(r'(\w+)(?:="([^"]*)")?')
def parse_opts(s):
    return {m.group(1): (m.group(2) if m.group(2) is not None else True) for m in ATTR.finditer(s or "")}

def render(text, ctx):
    def tag(mo):
        kind, slug, rest = mo.group(1), mo.group(2), mo.group(3)
        o = parse_opts(rest)
        if kind == "img":
            return img_html(slug, o.get("sizes", "100vw"), bool(o.get("eager")), o.get("pos"), o.get("class", ""), o.get("alt"))
        if kind == "fig":
            return fig_html(slug, o.get("ratio", "4x3"), o.get("sizes", "100vw"), o.get("caption"), o.get("pos"),
                            o.get("class", ""), bool(o.get("eager")), o.get("credit", "1") != "0")
        if kind == "credit":
            return credit_html(slug, o.get("prefix", "تصوير "))
        return mo.group(0)
    text = re.sub(r"\{\{(img|fig|credit) ([\w-]+)((?: \w+(?:=\"[^\"]*\")?)*)\}\}", tag, text)
    def var(mo):
        k = mo.group(1)
        return str(ctx.get(k, mo.group(0)))
    return re.sub(r"\{\{(\w+)\}\}", var, text)

def page_meta(raw):
    mo = re.match(r"\s*<!--meta\s*(\{.*?\})\s*-->", raw, re.S)
    meta = json.loads(mo.group(1)) if mo else {}
    body = raw[mo.end():] if mo else raw
    return meta, body

# ---------------------------------------------------------------- build
def main():
    if DIST.exists(): shutil.rmtree(DIST)
    (DIST / "assets").mkdir(parents=True)
    for d in ("css", "js", "fonts"):
        shutil.copytree(SRC / d, DIST / "assets" / d)
    shutil.copytree(SRC / "brand", DIST / "assets" / "brand")
    (DIST / "assets" / "brand" / "wordmark-inline.svg").unlink(missing_ok=True)
    (DIST / "assets" / "brand" / "wordmark.json").unlink(missing_ok=True)
    prepare_photos()
    v = hashlib.sha1(((SRC / "css" / "site.css").read_text() + (SRC / "js" / "site.js").read_text()).encode()).hexdigest()[:8]
    remote_slugs = sorted(s for s, p in PHOTO.items() if p["mode"] == "remote")
    remote = bool(remote_slugs)
    some = "بعض صور الموقع" if len(remote_slugs) < len(PHOTO) else "صور الموقع"
    base = dict(
        v=v, wordmark=wordmark, wa_digits=WA_DIGITS, wa_pretty=WA_PRETTY, site_url=SITE_URL,
        about_photos_note=about_photos_note(remote_slugs),
        icon_wa=ICONS["wa"], icon_check=ICONS["check"], icon_home=ICONS["home"], icon_eye=ICONS["eye"], icon_lock=ICONS["lock"],
        photos_note=(f"<li>الصور: تُحمَّل {some} من خدمة Unsplash، وقد ترى هذه الخدمة عنوان IP الخاص بك عند تحميل هذه الصور.</li>" if remote else ""),
    )
    head, header, footer = [(SRC / "partials" / f).read_text(encoding="utf-8") for f in ("head.html", "header.html", "footer.html")]
    pages = sorted((SRC / "pages").glob("*.html"))
    for p in pages:
        meta, body = page_meta(p.read_text(encoding="utf-8"))
        body = body.replace("{{dishes}}", dishes_markup())
        ctx = dict(base)
        used = set(re.findall(r"\{\{(?:img|fig) ([\w-]+)", body))
        ctx["preconnect"] = ('<link rel="preconnect" href="https://images.unsplash.com">\n'
                             if any(PHOTO[u]["mode"] == "remote" for u in used if u in PHOTO) else "")
        ctx.update(title=meta.get("title", "نَفَس"), og_title=meta.get("og_title", meta.get("title", "نَفَس")),
                   desc=meta.get("desc", ""), body_class=meta.get("body_class", ""),
                   base=f'<base href="{meta["base"]}">\n' if meta.get("base") else "")
        for k in ("cooks", "tasters", "about"):
            ctx[f"cur_{k}"] = ' aria-current="page"' if meta.get("nav") == k else ""
        out = render(head, ctx) + render(header, ctx) + '<main id="main">\n' + render(body, ctx) + "\n</main>\n" + render(footer, ctx)
        (DIST / p.name).write_text(out, encoding="utf-8")
    for f in ("_headers", "robots.txt", "site.webmanifest"):
        if (SRC / f).exists(): shutil.copy(SRC / f, DIST / f)
    local_note = "الصور محفوظة داخل الموقع نفسه بصيغة WebP وبعدة مقاسات (`assets/img`)"
    note = (f"{local_note}، ما عدا ما يلي فيُحمَّل مباشرة من خوادم Unsplash (الطريقة الرسمية لديهم): "
            + "، ".join(f"`{x}`" for x in remote_slugs) + "."
            if remote else local_note + ".")
    (DIST / "README.md").write_text((SRC / "README.md").read_text(encoding="utf-8").replace("{{photo_mode_note}}", note), encoding="utf-8")
    for f in ("favicon.svg", "favicon-32.png", "apple-touch-icon.png", "icon-192.png", "icon-512.png", "icon-maskable-512.png", "og.jpg"):
        if (SRC / "static" / f).exists(): shutil.copy(SRC / "static" / f, DIST / f)
    modes = {s: p["mode"] for s, p in PHOTO.items()}
    print("built", len(pages), "pages; photos:", modes)

if __name__ == "__main__":
    main()
