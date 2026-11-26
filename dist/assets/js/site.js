{
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const WA = ($('meta[name="nafas-whatsapp"]')?.content || '').replace(/\D/g, '');

  /* header: hairline after scrolling, mobile menu */
  const head = $('.site-head');
  const onScroll = () => head && head.classList.toggle('scrolled', window.scrollY > 8);
  window.addEventListener('scroll', onScroll, { passive: true }); onScroll();
  const menuBtn = $('.menu-btn'), nav = $('#site-nav');
  const setMenu = open => {
    if (!menuBtn || !nav) return;
    menuBtn.setAttribute('aria-expanded', String(open));
    nav.classList.toggle('open', open);
    menuBtn.querySelector('span').textContent = open ? 'سكّر' : 'القائمة';
  };
  menuBtn?.addEventListener('click', () => setMenu(menuBtn.getAttribute('aria-expanded') !== 'true'));
  document.addEventListener('keydown', e => { if (e.key === 'Escape' && nav?.classList.contains('open')) { setMenu(false); menuBtn.focus(); } });
  nav?.addEventListener('click', e => { if (e.target.closest('a')) setMenu(false); });

  /* photos: if a photo cannot load, keep the soft placeholder instead of a broken icon */
  const hideBroken = img => img.classList.add('gone');
  $$('.ph img').forEach(img => {
    if (img.complete && img.naturalWidth === 0) hideBroken(img);
    else img.addEventListener('error', () => hideBroken(img), { once: true });
  });

  /* taste demo: chips write the handwritten note on the order slip */
  $$('[data-taste]').forEach(box => {
    const note = $(box.dataset.taste), live = box.dataset.live ? $(box.dataset.live) : null;
    const empty = box.dataset.empty || 'على ذوقك: متل ما بتطبخها';
    const render = (announce) => {
      const on = $$('.chip[aria-pressed="true"]', box).map(c => c.dataset.v);
      const t = on.length ? 'على ذوقك: ' + on.join('، ') : empty;
      if (note) note.textContent = t;
      if (live && announce) live.textContent = t;
    };
    box.addEventListener('click', e => {
      const c = e.target.closest('.chip'); if (!c) return;
      c.setAttribute('aria-pressed', String(c.getAttribute('aria-pressed') !== 'true'));
      render(true);
    });
    render(false);
  });

  /* cooks page: the cook picks the changes she accepts; the customer's dish card follows */
  $$('[data-accept]').forEach(box => {
    const list = $(box.dataset.accept);
    const render = () => {
      const on = $$('.chip[aria-pressed="true"]', box).map(c => c.dataset.v);
      if (!list) return;
      list.innerHTML = on.length ? on.map(v => `<li>${v}</li>`).join('') : '<li class="empty">ما في تعديلات على هالطبق</li>';
    };
    box.addEventListener('click', e => {
      const c = e.target.closest('.chip'); if (!c) return;
      c.setAttribute('aria-pressed', String(c.getAttribute('aria-pressed') !== 'true'));
      render();
    });
    render();
  });

  /* forms: check, compose a WhatsApp message, keep a draft in this browser only */
  const normPhone = p => {
    let d = (p || '').replace(/[٠-٩]/g, ch => '٠١٢٣٤٥٦٧٨٩'.indexOf(ch)).replace(/[^\d+]/g, '');
    if (d.startsWith('+963')) d = '0' + d.slice(4);
    else if (d.startsWith('00963')) d = '0' + d.slice(5);
    else if (d.startsWith('963')) d = '0' + d.slice(3);
    else if (/^9\d{8}$/.test(d)) d = '0' + d;
    return /^09\d{8}$/.test(d) ? d : '';
  };
  const store = {
    get(k) { try { return JSON.parse(localStorage.getItem(k) || 'null'); } catch { return null; } },
    set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch {} },
    del(k) { try { localStorage.removeItem(k); } catch {} }
  };

  /* where the visitor came from: ?from=… (or utm_source) on any page, else the site that sent them.
     Kept in this browser so it still rides along if they open the form from another page. */
  const SRC = 'nafas-from';
  const cleanSrc = v => String(v || '').toLowerCase().replace(/[^a-z0-9._:-]/g, '').slice(0, 60);
  {
    const q = new URLSearchParams(location.search);
    const v = cleanSrc(q.get('from') || q.get('utm_source'));
    if (v) store.set(SRC, v);
    else if (!store.get(SRC) && document.referrer) {
      try {
        const h = new URL(document.referrer).hostname;
        if (h && h !== location.hostname) store.set(SRC, cleanSrc('ref:' + h));
      } catch {}
    }
  }

  /* tie each error message to its fields for screen readers */
  $$('form[data-wa] .field').forEach((f, i) => {
    const err = $('.err', f); if (!err) return;
    err.id = err.id || 'err-' + i;
    $$('input,textarea', f).forEach(el => el.setAttribute('aria-describedby', err.id));
  });

  $$('form[data-wa]').forEach(form => {
    const kind = form.dataset.wa;              // "cook" | "taster"
    const key = 'nafas-' + kind + '-draft';
    const card = form.closest('.form');
    const other = $('[data-other]', form);
    const otherWrap = other?.closest('.field');

    const read = () => {
      const fd = new FormData(form), o = {};
      for (const [k, v] of fd.entries()) {
        if (o[k] !== undefined) o[k] = [].concat(o[k], v); else o[k] = v;
      }
      return o;
    };
    const write = o => {
      if (!o) return;
      $$('input,textarea', form).forEach(el => {
        const v = o[el.name];
        if (v === undefined) return;
        if (el.type === 'checkbox' || el.type === 'radio') el.checked = [].concat(v).includes(el.value);
        else el.value = v;
      });
    };
    const syncOther = () => {
      const on = $('input[name="hood"][value="other"]', form)?.checked;
      if (otherWrap) otherWrap.hidden = !on;
    };
    write(store.get(key)); syncOther();
    form.addEventListener('input', () => { store.set(key, read()); syncOther(); });
    form.addEventListener('change', () => { store.set(key, read()); syncOther(); });

    const fail = (name, bad) => {
      const el = form.elements[name]; const f = (el?.length && !el.tagName ? el[0] : el)?.closest('.field');
      if (!f) return;
      f.classList.toggle('invalid', bad);
      $$('input,textarea', f).forEach(i => i.setAttribute('aria-invalid', String(bad)));
    };

    const compose = d => {
      const hood = d.hood === 'other' ? (d.hood_other || '').trim() : d.hood;
      const list = v => [].concat(v || []).filter(Boolean).join('، ');
      const L = [];
      if (kind === 'cook') {
        L.push('مرحبا نَفَس، بدي انضم كطاهية.');
        L.push('الاسم: ' + d.name.trim());
        L.push('الموبايل: ' + normPhone(d.phone));
        L.push('الحي: ' + hood);
        L.push('أطيب أطباقي: ' + d.dishes.trim());
        if (list(d.days)) L.push('الأيام يلي بقدر اطبخ فيها: ' + list(d.days));
        L.push('', 'رح ابعتلكن صورة أطيب طبخة عندي بهالمحادثة.');
      } else {
        L.push('مرحبا نَفَس، بدي سجّل بقائمة أول الذوّاقة.');
        L.push('الاسم: ' + d.name.trim());
        L.push('الموبايل: ' + normPhone(d.phone));
        L.push('الحي: ' + hood);
        if (list(d.miss)) L.push('مشتاق لـ: ' + list(d.miss));
        if (d.freq) L.push('بطلب أكل من برّا: ' + d.freq);
        const budget = (d.budget || '').trim(), bd = budget.replace(/[٠-٩]/g, ch => '٠١٢٣٤٥٦٧٨٩'.indexOf(ch));
        if (budget) L.push('بدفع عادة بوجبة الغدا: ' + (/^\d+$/.test(bd) ? bd + ' ل.س' : budget));
        if (d.pickup) L.push('الاستلام من مطبخ على بعد 10 دقايق: ' + d.pickup);
        if ((d.taste || '').trim()) L.push('ذوقي: ' + d.taste.trim());
      }
      return L.join('\n');
    };

    /* keep a copy with the host, so a signup is not lost if WhatsApp is never opened.
       Netlify Forms records it; anywhere else the request just fails quietly. */
    const save = d => {
      const flat = { 'form-name': form.getAttribute('name') || kind };
      for (const [k, v] of Object.entries(d)) {
        if (k === 'form-name') continue;
        flat[k] = [].concat(v).filter(Boolean).join('، ');
      }
      flat.phone = normPhone(d.phone) || flat.phone || '';
      if (d.hood === 'other') flat.hood = (d.hood_other || '').trim() || 'other';
      flat.from = store.get(SRC) || 'direct';
      const body = new URLSearchParams(flat).toString(), sentKey = 'nafas-sent-' + kind;
      try { if (sessionStorage.getItem(sentKey) === body) return; } catch {}
      fetch('/', { method: 'POST', headers: { 'Content-Type': 'application/x-www-form-urlencoded' }, body, keepalive: true })
        .then(r => { if (r.ok) { try { sessionStorage.setItem(sentKey, body); } catch {} } })
        .catch(() => {});
    };

    form.addEventListener('submit', e => {
      e.preventDefault();
      const d = read();
      const checks = {
        name: !(d.name || '').trim(),
        phone: !normPhone(d.phone),
        hood: !d.hood || (d.hood === 'other' && !(d.hood_other || '').trim()),
        consent: !d.consent,
      };
      if (kind === 'cook') checks.dishes = !(d.dishes || '').trim();
      let first = null;
      for (const [k, bad] of Object.entries(checks)) {
        if (k === 'hood') {
          fail('hood', !d.hood);
          fail('hood_other', d.hood === 'other' && !(d.hood_other || '').trim());
        } else fail(k, bad);
        if (bad && !first) first = (k === 'hood' && d.hood === 'other') ? 'hood_other' : k;
      }
      if (first) {
        const el = form.elements[first];
        (el?.length && !el.tagName ? el[0] : el)?.focus();
        return;
      }
      if ((d['bot-field'] || '').trim()) return;   // a bot filled the hidden field
      const text = compose(d);
      save(d);
      const link = $('[data-wa-link]', card);
      if (link) link.href = 'https://wa.me/' + WA + '?text=' + encodeURIComponent(text);
      const pre = $('[data-preview]', card); if (pre) pre.textContent = text;
      card.classList.add('sent');
      const done = $('.done', card); done?.setAttribute('tabindex', '-1'); done?.focus();
      card.scrollIntoView({ block: 'start', behavior: 'smooth' });
    });

    $('[data-copy]', card)?.addEventListener('click', async ev => {
      const btn = ev.currentTarget, text = $('[data-preview]', card)?.textContent || '';
      try { await navigator.clipboard.writeText(text); btn.textContent = 'انسخت الرسالة'; }
      catch { const r = document.createRange(); r.selectNodeContents($('[data-preview]', card)); const s = getSelection(); s.removeAllRanges(); s.addRange(r); btn.textContent = 'حدّدتلك الرسالة، انسخها'; }
    });
    $('[data-edit]', card)?.addEventListener('click', () => { card.classList.remove('sent'); form.elements.name?.focus(); });
  });
}
