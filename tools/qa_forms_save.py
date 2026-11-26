"""Checks the Netlify Forms copy of each signup and the visit-source code.

Run with the local server on :8766 (python3 -m http.server 8766 --directory dist).
POSTs to "/" are intercepted here, so nothing leaves the machine.
"""
import asyncio
from urllib.parse import parse_qs

from playwright.async_api import async_playwright

BASE = "http://localhost:8766"
results = []


def ok(cond, label):
    results.append((bool(cond), label))
    print(("PASS " if cond else "FAIL ") + label)


async def new_page(browser, posts):
    ctx = await browser.new_context(viewport={"width": 390, "height": 844})
    pg = await ctx.new_page()
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))

    async def handle(route, request):
        if request.method == "POST":
            posts.append({k: v[0] for k, v in parse_qs(request.post_data or "").items()})
            await route.fulfill(status=200, body="ok")
        else:
            await route.continue_()

    await pg.route(BASE + "/", handle)
    return ctx, pg, errs


async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch()

        # 1) a code in the link on the home page rides along to the tasters form
        posts = []
        ctx, pg, errs = await new_page(b, posts)
        await pg.goto(BASE + "/index.html?from=FB-Mezzeh")
        await pg.goto(BASE + "/tasters.html")
        await pg.fill("#t-name", "سامر")
        await pg.fill("#t-phone", "٠٩٤٤١٢٣٤٥٦")
        await pg.check('input[name=hood][value="المزة"]')
        await pg.check('input[name=miss][value="كبة"]')
        await pg.check('input[name=miss][value="حرّاق إصبعو"]')
        await pg.fill("#t-budget", "٢٥٠")
        await pg.check('input[name=pickup][value="أكيد"]')
        await pg.check("input[name=consent]")
        await pg.click('form[name=tasters] button[type=submit]')
        await pg.wait_for_timeout(500)
        ok(len(posts) == 1, "tasters: one POST to the host")
        d = posts[0] if posts else {}
        ok(d.get("form-name") == "tasters", "tasters: form-name")
        ok(d.get("from") == "fb-mezzeh", "tasters: source code kept across pages, lower-cased")
        ok(d.get("phone") == "0944123456", "tasters: phone normalised")
        ok(d.get("miss") == "كبة، حرّاق إصبعو", "tasters: dishes joined")
        ok(d.get("pickup") == "أكيد" and d.get("budget") == "٢٥٠", "tasters: pickup + budget sent")
        ok(d.get("hood") == "المزة", "tasters: hood")
        msg = await pg.inner_text("form[name=tasters] ~ .done [data-preview]") if await pg.query_selector("form[name=tasters] ~ .done [data-preview]") else await pg.inner_text("[data-preview]")
        ok("بدفع عادة بوجبة الغدا: 250 ل.س" in msg, "tasters: budget line in WhatsApp message")
        ok("الاستلام من مطبخ على بعد 10 دقايق: أكيد" in msg, "tasters: pickup line in WhatsApp message")
        ok("from" not in msg and "fb-mezzeh" not in msg, "tasters: source code not in the WhatsApp message")
        # same answers again: no second copy
        await pg.click("[data-edit]")
        await pg.click('form[name=tasters] button[type=submit]')
        await pg.wait_for_timeout(400)
        ok(len(posts) == 1, "tasters: identical resubmit not saved twice")
        ok(not errs, "tasters: no script errors " + "; ".join(errs))
        await ctx.close()

        # 2) no code: the referring site is used; 'other' hood resolves to its name
        posts = []
        ctx, pg, errs = await new_page(b, posts)
        await pg.goto(BASE + "/cooks.html", referer="https://l.facebook.com/")
        await pg.fill("#c-name" if await pg.query_selector("#c-name") else 'form[name=cooks] input[name=name]', "أم خالد")
        await pg.fill('form[name=cooks] input[name=phone]', "+963 944 123 456")
        await pg.check('form[name=cooks] input[name=hood][value="other"]')
        await pg.fill('form[name=cooks] input[name=hood_other]', "المالكي")
        await pg.fill('form[name=cooks] [name=dishes]', "يالنجي، كبة لبنية")
        await pg.check('form[name=cooks] input[name=days][value="السبت"]')
        await pg.check('form[name=cooks] input[name=days][value="الأحد"]')
        await pg.check('form[name=cooks] input[name=consent]')
        await pg.click('form[name=cooks] button[type=submit]')
        await pg.wait_for_timeout(500)
        d = posts[0] if posts else {}
        ok(len(posts) == 1 and d.get("form-name") == "cooks", "cooks: one POST, form-name")
        ok(d.get("from") == "ref:l.facebook.com", "cooks: referrer used when no code")
        ok(d.get("hood") == "المالكي" and d.get("hood_other") == "المالكي", "cooks: other hood resolved")
        ok(d.get("days") == "السبت، الأحد", "cooks: days joined")
        ok(d.get("phone") == "0944123456", "cooks: phone normalised")
        ok(not errs, "cooks: no script errors " + "; ".join(errs))
        await ctx.close()

        # 3) a bot that fills the hidden field gets nothing and nothing is saved
        posts = []
        ctx, pg, errs = await new_page(b, posts)
        await pg.goto(BASE + "/tasters.html")
        await pg.fill("#t-name", "bot")
        await pg.fill("#t-phone", "0944123456")
        await pg.check('input[name=hood][value="المزة"]')
        await pg.check("input[name=consent]")
        await pg.evaluate("document.querySelector('form[name=tasters] [name=\"bot-field\"]').value='spam'")
        await pg.click('form[name=tasters] button[type=submit]')
        await pg.wait_for_timeout(400)
        sent = await pg.evaluate("document.querySelector('form[name=tasters]').closest('.form').classList.contains('sent')")
        ok(not posts and not sent, "honeypot: nothing saved, no message")
        ok(await pg.is_hidden("form[name=tasters] .hp"), "honeypot: hidden from people")
        await ctx.close()

        # 4) direct visit with no code and no referrer
        posts = []
        ctx, pg, errs = await new_page(b, posts)
        await pg.goto(BASE + "/tasters.html")
        await pg.fill("#t-name", "رنا")
        await pg.fill("#t-phone", "0933123456")
        await pg.check('input[name=hood][value="البرامكة"]')
        await pg.check("input[name=consent]")
        await pg.click('form[name=tasters] button[type=submit]')
        await pg.wait_for_timeout(400)
        ok(posts and posts[0].get("from") == "direct", "direct visit marked direct")
        await ctx.close()
        await b.close()

    bad = [l for c, l in results if not c]
    print(f"\n{len(results) - len(bad)}/{len(results)} passed")


asyncio.run(main())
