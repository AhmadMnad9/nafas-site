import asyncio, urllib.parse
from playwright.async_api import async_playwright
B="http://127.0.0.1:8766/"
ok=lambda c,m: print(("PASS " if c else "FAIL ")+m)
async def main():
    async with async_playwright() as p:
        b=await p.chromium.launch()
        ctx=await b.new_context(viewport={"width":390,"height":844})
        pg=await ctx.new_page(); errs=[]
        pg.on("pageerror", lambda e: errs.append(str(e)))
        # menu
        await pg.goto(B+"index.html")
        ok(not await pg.is_visible("#site-nav .nav-list"), "menu hidden on load (mobile)")
        await pg.click(".menu-btn"); ok(await pg.is_visible("#site-nav .nav-list"), "menu opens")
        ok(await pg.get_attribute(".menu-btn","aria-expanded")=="true", "aria-expanded true")
        await pg.keyboard.press("Escape"); ok(not await pg.is_visible("#site-nav .nav-list"), "Escape closes menu")
        # home taste chips
        await pg.click('.chip[data-v="حامض زيادة"]')
        t=await pg.text_content("#home-note"); ok("حامض زيادة" in t and "ملح خفيف" in t, "home note: "+t)
        ok("حامض زيادة" in (await pg.text_content("#home-note-live")), "live region announces")
        for v in ["ملح خفيف","بلا بصل","حامض زيادة"]: await pg.click(f'.chip[data-v="{v}"]')
        ok((await pg.text_content("#home-note")).strip()=="على ذوقك: متل ما بتطبخها", "empty note text")
        # cooks accept chips
        await pg.goto(B+"cooks.html")
        ok("ملح خفيف" in await pg.inner_text("#mods"), "mods initial")
        await pg.click('.chip[data-v="بدون ثوم"]'); ok("بدون ثوم" in await pg.inner_text("#mods"), "mods add")
        for v in ["ملح خفيف","بدون بصل","بدون ثوم"]: await pg.click(f'[data-accept] .chip[data-v="{v}"]')
        ok("ما في تعديلات" in await pg.inner_text("#mods"), "mods empty state")
        # cooks form validation
        await pg.click('form[data-wa="cook"] button[type=submit]')
        inv=await pg.eval_on_selector_all('form[data-wa="cook"] .field.invalid', "els=>els.length")
        ok(inv==5, f"5 invalid fields on empty submit (got {inv})")
        await pg.fill("#c-name","أم خالد"); await pg.fill("#c-phone","12345")
        await pg.check('input[name=hood][value=other]'); ok(await pg.is_visible("#c-hood"), "other hood field shows")
        await pg.click('form[data-wa="cook"] button[type=submit]')
        ok(await pg.eval_on_selector("#c-phone","e=>e.closest('.field').classList.contains('invalid')"), "bad phone rejected")
        ok(await pg.eval_on_selector("#c-hood","e=>e.closest('.field').classList.contains('invalid')"), "empty other hood rejected")
        ok(not await pg.eval_on_selector('input[name=hood]',"e=>e.closest('.field').classList.contains('invalid')"), "hood group ok once chosen")
        await pg.fill("#c-phone","+963 944 123 456"); await pg.fill("#c-hood","المالكي"); await pg.fill("#c-dishes","يالنجي، كبة لبنية")
        await pg.check('input[name=days][value="السبت"]'); await pg.check('input[name=days][value="الأحد"]')
        await pg.check('form[data-wa="cook"] input[name=consent]')
        # draft restore
        await pg.reload(); ok(await pg.input_value("#c-name")=="أم خالد" and await pg.is_checked('input[name=days][value="الأحد"]'), "draft restored after reload")
        ok(await pg.is_visible("#c-hood"), "other hood visible after restore")
        await pg.click('form[data-wa="cook"] button[type=submit]')
        ok(await pg.eval_on_selector('form[data-wa="cook"]',"f=>f.closest('.form').classList.contains('sent')"), "cook form sent state")
        href=await pg.get_attribute('[data-wa-link]','href')
        ok(href.startswith("https://wa.me/963962934928?text="), "wa link target")
        msg=urllib.parse.unquote(href.split("text=")[1]); print("---\n"+msg+"\n---")
        ok("0944123456" in msg and "المالكي" in msg and "السبت، الأحد" in msg, "cook message content")
        ok(await pg.is_visible(".done"), "done panel visible")
        await pg.click("[data-edit]"); ok(await pg.is_visible("#c-name"), "edit returns to form")
        # tasters
        await pg.goto(B+"tasters.html")
        await pg.fill("#t-name","رنا"); await pg.fill("#t-phone","٠٩٤٤١٢٣٤٥٦")
        await pg.check('input[name=hood][value="المزة"]'); await pg.check('input[name=miss][value="كبة"]'); await pg.check('input[name=miss][value="ملوخية"]')
        await pg.check('input[name=freq][value="مرة بالأسبوع"]'); await pg.fill("#t-taste","ملح خفيف، بلا كزبرة")
        await pg.check('form[data-wa="taster"] input[name=consent]')
        await pg.click('form[data-wa="taster"] button[type=submit]')
        href=await pg.get_attribute('[data-wa-link]','href'); msg=urllib.parse.unquote(href.split("text=")[1]); print("---\n"+msg+"\n---")
        ok("0944123456" in msg and "كبة، ملوخية" in msg and "مرة بالأسبوع" in msg, "taster message content (Arabic-Indic digits ok)")
        ok(not errs, "no page errors "+str(errs))
        await b.close()
asyncio.run(main())
