/* Shared topic-page behavior (Christian Curator). No framework.
   Loaded with `defer` on every docs/topics/<slug>/ page by scripts/build_topic_top.py.

   1. Click tracking: one delegated GA4 `article_click` listener, the same event
      the homepage sends (link_url feeds the Link URL dimension that
      scripts/fetch_click_counts.py reads), plus `position` from data-pos.
      Links in existing hand-curated blocks get data-pos here at load, so those
      blocks need no markup change:
        .cc-article-entry          topic-curated
        .cc-topic-voices, .cc-debate-thinkers   topic-voices
        .cc-recent                 topic-latest
        .cc-debate-reads           topic-debate
        .cc-related-topics         topic-related
        .cc-latest-figures         topic-figures
      Blocks written by build_topic_top.py carry data-pos in the HTML
      (topic-jump, topic-glance, topic-start, topic-latest, topic-share, ...).
   2. Copy-link buttons beside every section heading that has an id.
   3. Share: navigator.share on phones, clipboard copy of a short summary elsewhere.
   4. Copy key number, print handout, inline Daily Digest signup.
   GA4 events: article_click, share {method, item}, signup {method, source}.
   No tracking parameters are ever added to copied or shared links. */
(function () {
  'use strict';
  var doc = document;
  var main = doc.querySelector('main.cc-prose') || doc.body;
  var slug = (location.pathname.match(/\/topics\/([^\/]+)\//) || [])[1] || '';
  var pageUrl = location.origin + location.pathname;

  function ga(name, params) {
    if (typeof window.gtag === 'function') window.gtag('event', name, params);
  }

  // ---- 1. click tracking ------------------------------------------------
  var AUTO_POS = [
    ['.cc-article-entry a', 'topic-curated'],
    ['.cc-topic-voices a', 'topic-voices'],
    ['.cc-debate-thinkers a', 'topic-voices'],
    ['.cc-recent a', 'topic-latest'],
    ['.cc-debate-reads a', 'topic-debate'],
    ['.cc-related-topics a', 'topic-related'],
    ['.cc-latest-figures a', 'topic-figures']
  ];
  AUTO_POS.forEach(function (pair) {
    var links = main.querySelectorAll(pair[0]);
    for (var i = 0; i < links.length; i++) {
      if (!links[i].hasAttribute('data-pos')) links[i].setAttribute('data-pos', pair[1]);
    }
  });
  doc.addEventListener('click', function (e) {
    var a = e.target.closest && e.target.closest('a[data-pos]');
    if (!a) return;
    ga('article_click', {
      article_title: a.textContent.trim().slice(0, 100),
      article_source: a.getAttribute('data-src') || '',
      position: a.getAttribute('data-pos'),
      topic: slug,
      link_url: a.href,
      transport_type: 'beacon'
    });
  });

  // ---- clipboard helper ---------------------------------------------------
  function copyText(text) {
    if (navigator.clipboard && window.isSecureContext) {
      return navigator.clipboard.writeText(text);
    }
    return new Promise(function (resolve, reject) {
      var ta = doc.createElement('textarea');
      ta.value = text;
      ta.setAttribute('readonly', '');
      ta.style.position = 'absolute';
      ta.style.left = '-9999px';
      doc.body.appendChild(ta);
      ta.select();
      try { doc.execCommand('copy') ? resolve() : reject(); } catch (err) { reject(err); }
      doc.body.removeChild(ta);
    });
  }
  function flash(btn, label) {
    var original = btn.getAttribute('data-label') || btn.textContent;
    btn.setAttribute('data-label', original);
    btn.textContent = label;
    btn.setAttribute('data-done', '');
    setTimeout(function () { btn.textContent = original; btn.removeAttribute('data-done'); }, 1800);
  }

  // ---- 2. copy-link anchors on section headings ---------------------------
  function headingFor(el) {
    if (/^H[23]$/.test(el.tagName)) return el;
    return el.querySelector('h2, h3, .cc-tt-label, .cc-debate-position-name, .cc-debate-name, .cc-chart-kicker, .cc-viz-kicker');
  }
  var targets = main.querySelectorAll('[id]');
  for (var t = 0; t < targets.length; t++) {
    var el = targets[t];
    if (el.closest('.cc-tt-jump, .cc-chart-svg, .cc-viz-svg, svg, form, details') || el.tagName === 'INPUT') continue;
    if (/^(bl-|cc-signup)/.test(el.id)) continue;
    var h = headingFor(el);
    if (!h || h.querySelector('.cc-tt-anchor')) continue;
    var b = doc.createElement('button');
    b.type = 'button';
    b.className = 'cc-tt-anchor';
    b.textContent = 'Copy link';
    b.setAttribute('data-anchor', el.id);
    b.setAttribute('aria-label', 'Copy a link to this section');
    h.appendChild(b);
  }

  // ---- print footer with the page address ---------------------------------
  var pu = doc.createElement('p');
  pu.className = 'cc-tt-print-url';
  pu.textContent = 'Christian Curator: ' + pageUrl.replace(/^https?:\/\//, '');
  main.appendChild(pu);
  window.addEventListener('beforeprint', function () { ga('share', { method: 'print', item: slug }); });

  // ---- 3 and 4. buttons ----------------------------------------------------
  doc.addEventListener('click', function (e) {
    var btn = e.target.closest && e.target.closest('button');
    if (!btn) return;
    if (btn.classList.contains('cc-tt-anchor')) {
      var id = btn.getAttribute('data-anchor');
      copyText(pageUrl + '#' + id).then(function () { flash(btn, 'Copied'); });
      ga('share', { method: 'copy_link', item: id });
      return;
    }
    var action = btn.getAttribute('data-cc-action');
    if (action === 'share') {
      var summary = btn.getAttribute('data-share-text') || doc.title;
      var item = btn.getAttribute('data-share-item') || 'page';
      if (navigator.share && /Android|iPhone|iPad|iPod/i.test(navigator.userAgent)) {
        navigator.share({ title: doc.title, text: summary, url: pageUrl }).then(function () {
          ga('share', { method: 'native', item: item });
        }).catch(function () {});
      } else {
        copyText(summary + '\n' + pageUrl).then(function () { flash(btn, 'Summary copied'); });
        ga('share', { method: 'copy_summary', item: item });
      }
    } else if (action === 'copy-stat') {
      copyText(btn.getAttribute('data-copy') || '').then(function () { flash(btn, 'Copied'); });
      ga('share', { method: 'copy_stat', item: 'key-number' });
    } else if (action === 'print') {
      window.print();
    }
  });

  // ---- inline Daily Digest signup ------------------------------------------
  // Same Worker and reCAPTCHA key as the homepage form (frontend/template.html).
  var form = doc.querySelector('form.cc-tt-signup-form');
  if (form) {
    var WORKER_URL = 'https://orange-bird-0b93.tdaly678.workers.dev/';
    var SITE_KEY = '6LfNEL4sAAAAAMOuBd1AqaSaL6GLd9WnkOXSjkMV';
    var msg = form.parentNode.querySelector('.cc-tt-signup-msg');
    var submit = form.querySelector('button');
    var loaded = false;
    function loadCaptcha() {
      if (loaded) return;
      loaded = true;
      var s = doc.createElement('script');
      s.src = 'https://www.google.com/recaptcha/api.js?render=' + SITE_KEY;
      s.async = true;
      doc.head.appendChild(s);
    }
    function say(text, ok) {
      msg.textContent = text;
      msg.className = 'cc-tt-signup-msg ' + (ok ? 'is-ok' : 'is-err');
    }
    form.addEventListener('focusin', loadCaptcha);
    form.addEventListener('submit', function (e) {
      e.preventDefault();
      loadCaptcha();
      var email = (form.email.value || '').trim();
      var source = form.source.value || ('topic:' + slug);
      if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) { say('Please enter a valid email address.'); return; }
      submit.disabled = true;
      var tries = 0;
      (function go() {
        if (typeof grecaptcha === 'undefined' || !grecaptcha.ready) {
          if (++tries > 30) { say('Verification is still loading. Please try again in a moment.'); submit.disabled = false; return; }
          return setTimeout(go, 200);
        }
        grecaptcha.ready(function () {
          grecaptcha.execute(SITE_KEY, { action: 'subscribe' }).then(function (token) {
            return fetch(WORKER_URL, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ email: email, token: token, honeypot: form.honeypot.value || '', source: source })
            });
          }).then(function (resp) {
            return resp.json().then(function (data) { return { ok: resp.ok, data: data }; });
          }).then(function (res) {
            if (res.ok && res.data && res.data.success) {
              form.style.display = 'none';
              say(res.data.alreadySubscribed ? 'You are already subscribed. Thank you.' : 'You are subscribed. Check your inbox for a confirmation email.', true);
              ga('signup', { method: 'email', source: source });
            } else {
              say((res.data && res.data.error) || 'Signup failed. Please try again.');
              submit.disabled = false;
            }
          }).catch(function () { say('Network error. Please try again.'); submit.disabled = false; });
        });
      })();
    });
  }
})();
