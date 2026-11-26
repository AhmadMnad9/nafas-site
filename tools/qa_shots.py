import asyncio, sys, json
from playwright.async_api import async_playwright
BASE="http://127.0.0.1:8766/"
pages=sys.argv[1].split(",")
sizes=[tuple(map(int,s.split("x"))) for s in sys.argv[2].split(",")]
theme=sys.argv[3] if len(sys.argv)>3 else "light"
async def main():
    async with async_playwright() as p:
        b=await p.chromium.launch()
        for w,h in sizes:
            ctx=await b.new_context(viewport={"width":w,"height":h}, color_scheme=theme, device_scale_factor=1)
            pg=await ctx.new_page()
            errs=[]; pg.on("console", lambda m: errs.append(m.text) if m.type=="error" else None); pg.on("pageerror", lambda e: errs.append(str(e)))
            for name in pages:
                await pg.goto(BASE+name, wait_until="load"); await pg.wait_for_timeout(500)
                sw=await pg.evaluate("document.documentElement.scrollWidth")
                out=f"/tmp/qa_{name.replace('.html','')}_{w}_{theme}.png"
                await pg.screenshot(path=out, full_page=True)
                real=[e for e in errs if 'images.unsplash.com' not in e and 'ERR_' not in e]
                print(name, w, "scrollWidth", sw, "errors", real[:3])
                errs.clear()
            await ctx.close()
        await b.close()
asyncio.run(main())
