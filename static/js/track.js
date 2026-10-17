/* OverlapIQ shared analytics (GA4). Loaded on every page: <script defer src="/js/track.js?v=1">.
 * Needs the gtag snippet already on the page. Every custom event carries page_type and content_group.
 * Events: content_view, scroll_depth, time_on_page, read_complete, internal_link_click, analyzer_cta_click,
 *         toc_click, outbound_click, faq_open, panel_toggle, js_error (+ tool events fired from index.html via window.oiqTrack).
 * Safe by design: every call is wrapped so analytics can never break the page. */
(function () {
  'use strict';
  if (window.__oiqTrack) return;
  window.__oiqTrack = true;

  var path = (location.pathname.replace(/\/+$/, '') || '/');
  var slug = path.indexOf('/blog/') === 0 ? path.slice(6) : '';
  var pageType = path === '/' ? 'home'
    : path === '/blog' ? 'blog_index'
    : slug ? 'blog_post'
    : path === '/xray' ? 'tool'
    : (path === '/learn' || path.indexOf('/learn/') === 0) ? 'learn'
    : /^\/(international|sif|gift-city|reits)$/.test(path) ? 'hub' : 'other';

  function groupOf() {
    var p = path + ' ' + slug;
    if (path === '/xray') return 'xray';
    if (path === '/learn' || path.indexOf('/learn/') === 0) return 'learn';
    if (/gift|lrs/.test(p)) return 'gift-city';
    if (/sif|long-short/.test(p)) return 'sif';
    if (/reit|invit/.test(p)) return 'reits';
    if (/international|vested|indmoney|ibkr|global|nasdaq|world|emerging|us-stock|overseas|foreign/.test(p)) return 'international';
    return 'mutual-funds';
  }
  var group = path === '/' ? 'home' : groupOf();

  var debug = /[?&]debug_mode=(1|true)\b/.test(location.search);

  function ev(name, params) {
    try {
      if (typeof window.gtag !== 'function') return;
      var p = params || {};
      if (debug) p.debug_mode = true; // shows the event in GA4 > Admin > DebugView
      p.page_type = pageType;
      p.content_group = group;
      window.gtag('event', name, p);
    } catch (e) { /* never break the page */ }
  }
  window.oiqTrack = ev;

  function clip(s, n) { return String(s || '').replace(/\s+/g, ' ').trim().slice(0, n || 80); }

  // ---- one event per page view with context, so reports can be sliced by page type and topic
  ev('content_view', { slug: slug || path });

  // ---- scroll depth + engaged time (home already has its own inline versions)
  var engaged = 0, marks = {}, readDone = false;
  if (pageType !== 'home') {
    var onScroll = function () {
      var h = document.documentElement.scrollHeight - window.innerHeight;
      if (h <= 0) return;
      var pct = Math.round((window.scrollY / h) * 100);
      [25, 50, 75, 100].forEach(function (m) {
        if (pct >= m && !marks[m]) { marks[m] = true; ev('scroll_depth', { depth: m }); maybeRead(); }
      });
    };
    var t = null;
    window.addEventListener('scroll', function () { if (t) return; t = setTimeout(function () { t = null; onScroll(); }, 200); }, { passive: true });
    var stops = [30, 60, 120, 300];
    setInterval(function () {
      if (document.visibilityState !== 'visible') return;
      engaged++;
      if (stops.indexOf(engaged) > -1) ev('time_on_page', { seconds: engaged });
      maybeRead();
    }, 1000);
  } else {
    setInterval(function () { if (document.visibilityState === 'visible') engaged++; }, 1000);
  }
  function maybeRead() {
    // a real read: scrolled most of the way AND spent at least 45 seconds
    if (readDone || pageType !== 'blog_post') return;
    if (marks[75] && engaged >= 45) { readDone = true; ev('read_complete', { slug: slug, seconds: engaged }); }
  }

  // ---- link clicks
  function sectionOf(el) {
    var q = el;
    while (q && q !== document.body) {
      var tag = q.tagName;
      if (tag === 'HEADER') return 'header';
      if (tag === 'FOOTER') return 'footer';
      if (q.id) return q.id;
      q = q.parentElement;
    }
    return 'body';
  }
  document.addEventListener('click', function (e) {
    try {
      var a = e.target && e.target.closest ? e.target.closest('a[href]') : null;
      if (!a) return;
      var raw = a.getAttribute('href') || '';
      var text = clip(a.getAttribute('data-track') || a.textContent || a.getAttribute('aria-label'), 60);
      if (raw.charAt(0) === '#') { ev('toc_click', { anchor: raw.slice(1, 40), link_text: text }); return; }
      if (/^(mailto|tel):/i.test(raw)) return;
      var u = new URL(a.href, location.href);
      if (u.origin !== location.origin) {
        ev('outbound_click', { link_domain: u.hostname, link_url: clip(u.href, 100), link_text: text, section: sectionOf(a) });
        return;
      }
      var dest = (u.pathname.replace(/\/+$/, '') || '/') + u.search;
      var d = u.pathname.replace(/\/+$/, '') || '/';
      var sec = sectionOf(a);
      var logoLink = d === '/' && !u.search && !u.hash && (sec === 'header' || sec === 'footer');   // brand/logo link is navigation, not a CTA
      var type = logoLink ? 'home' : d === '/' ? 'analyzer' : d === '/xray' ? 'tool' : (d === '/learn' || d.indexOf('/learn/') === 0) ? 'learn' : /^\/(international|sif|gift-city|reits)$/.test(d) ? 'hub' : d.indexOf('/blog') === 0 ? 'blog' : 'other';
      var params = { link_url: clip(dest, 100), link_text: text, link_type: type, section: sec };
      ev('internal_link_click', params);
      if (type === 'analyzer') ev('analyzer_cta_click', params);
    } catch (err) { /* ignore */ }
  }, true);

  // ---- expandable sections: FAQs count as faq_open, anything tagged data-track-name is a panel
  document.addEventListener('toggle', function (e) {
    try {
      var d = e.target;
      if (!d || d.tagName !== 'DETAILS') return;
      var name = d.getAttribute('data-track-name');
      var s = d.querySelector('summary');
      if (name) { ev('panel_toggle', { panel: name, open: d.open ? 1 : 0 }); return; }
      if (d.open) ev('faq_open', { question: clip(s ? s.textContent : '', 90) });
    } catch (err) { /* ignore */ }
  }, true);

  // ---- JS errors (max 3 per page) so a broken tool shows up in analytics, not just in support emails
  var errs = 0;
  window.addEventListener('error', function (e) {
    if (errs++ >= 3) return;
    ev('js_error', { message: clip(e && e.message, 90), script_file: clip(e && e.filename ? e.filename.split('/').pop() : '', 40) });
  });
})();
