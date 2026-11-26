"""Render PNG icons and the social share image (og.jpg) with Chromium."""
import asyncio
from pathlib import Path
from playwright.async_api import async_playwright
SRC = Path("/home/claude/nafas/site2/src"); ST = SRC / "static"; BR = SRC / "brand"
icon = (BR / "nafas-icon.svg").read_text(); mask = (BR / "nafas-icon-maskable.svg").read_text()
wm_light = (BR / "nafas-wordmark-light.svg").read_text()
def page(svg, size): return f'<!doctype html><html><body style="margin:0;width:{size}px;height:{size}px;overflow:hidden;background:transparent">{svg.replace("<svg ", f"<svg width={size} height={size} ",1)}</body></html>'
OG = f'''<!doctype html><html lang="ar" dir="rtl"><head><meta charset="utf-8"><style>
@font-face{{font-family:Cairo;src:url(file://{SRC}/fonts/cairo.woff2) format("woff2");font-weight:200 1000}}
html,body{{margin:0}}
body{{width:1200px;height:630px;background:#240805;color:#FBF1EA;font-family:Cairo;position:relative;overflow:hidden}}
.ph{{position:absolute;left:0;top:0;width:560px;height:630px;background:url(file://{SRC}/photos/hero-hands.jpg) 50% 44%/cover no-repeat}}
.ph::after{{content:"";position:absolute;inset:0;background:linear-gradient(to right,rgba(36,8,5,0) 62%,#240805 100%)}}
.t{{position:absolute;right:84px;top:118px;width:560px}}
.t svg{{height:138px;width:auto;display:block}}
h1{{font-size:62px;font-weight:900;line-height:1.22;margin:30px 0 0}}
p{{font-size:27px;color:#F8705B;font-weight:700;margin:18px 0 0}}
</style></head><body>
<div class="ph"></div>
<div class="t">{wm_light}<h1>أكل البيت،<br>على ذوقك.</h1><p>قريباً بالمزة والبرامكة، دمشق</p></div>
</body></html>'''
async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch()
        for name, svg, size in [("favicon-32.png", icon, 32), ("icon-192.png", icon, 192), ("icon-512.png", icon, 512),
                                ("icon-maskable-512.png", mask, 512), ("apple-touch-icon.png", mask, 180)]:
            pg = await b.new_page(viewport={"width": size, "height": size})
            await pg.set_content(page(svg, size)); await pg.screenshot(path=str(ST / name), omit_background=True); await pg.close()
        pg = await b.new_page(viewport={"width": 1200, "height": 630})
        tmp = Path("/tmp/nafas-og.html"); tmp.write_text(OG, encoding="utf-8")
        await pg.goto("file://" + str(tmp)); await pg.evaluate("document.fonts.ready"); await pg.wait_for_timeout(300)
        await pg.screenshot(path=str(ST / "og.jpg"), type="jpeg", quality=86); await pg.close()
        await b.close()
asyncio.run(main())
print("static ok")
