/* OverlapIQ Portfolio X-Ray (v13). Runs entirely in the browser: the amounts you enter never leave your device.
 * Only fund IDs are sent to our own API, to fetch each fund's published holdings.
 * Needs /js/xray-data.js (window.XR) and /api/xray/index + /api/holdings/<id>. */
(function () {
  'use strict';
  var XR = window.XR;
  if (!XR) { return; }
  var $ = function (id) { return document.getElementById(id); };
  var STORE = 'overlapiq_xray_v1';
  var NOT_ITEMISED = '(not itemised)';
  var USD_THRESHOLD = 60000;      // US estate-tax filing threshold for non-resident aliens (USD)
  var BRACKETS = [[10000, .18], [20000, .20], [40000, .22], [60000, .24], [80000, .26], [100000, .28], [150000, .30], [250000, .32], [500000, .34], [750000, .37], [1000000, .39], [Infinity, .40]];
  var SCHEMES = [];               // [{id,name,amc,category,tick:[...],toks:Set}]
  var positions = [];             // [{uid, raw, amount (in entry currency), kind, id, stock, label, cands}]
  var holdingsCache = {};
  var uidN = 0;
  var lastResult = null;

  function track(name, params) { try { if (window.oiqTrack) window.oiqTrack(name, params || {}); } catch (e) { } }
  function esc(s) { return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]; }); }
  function inr(n) { return '₹' + Math.round(n).toLocaleString('en-IN'); }
  function pct(n, d) { return (n).toFixed(d == null ? 1 : d) + '%'; }
  function fx() { var v = parseFloat($('xrFx').value); return isFinite(v) && v > 0 ? v : XR.fx; }
  function entryCcy() { return $('xrCcy').value; }

  // ------------------------------------------------------------------ names and keys
  var SUFFIX = /(ltd|limited|inc|incorporated|corp|corporation|co|company|plc|nv|sa|ag|se|spa|llc|holdings?|group)$/;
  function normKey(name) {
    var s = String(name || '').toLowerCase().replace(/&/g, ' and ').replace(/\bthe\b/g, ' ');
    s = s.replace(/\bcorporation\b/g, 'corp').replace(/\bcompany\b/g, 'co').replace(/\blimited\b/g, 'ltd').replace(/\bincorporated\b/g, 'inc');
    return s.replace(/[^a-z0-9]+/g, '');
  }
  function coreKey(name) {   // key without the legal suffix, for loose company matching
    var k = normKey(name), prev = '';
    while (k !== prev) { prev = k; k = k.replace(SUFFIX, ''); }
    return k;
  }
  var STOP = { fund: 1, plan: 1, direct: 1, regular: 1, growth: 1, option: 1, idcw: 1, dividend: 1, scheme: 1, mutual: 1, the: 1, of: 1, g: 1, dp: 1, gr: 1, 'in': 1, reinvestment: 1, payout: 1, and: 1, etf: 0 };
  function toks(s) {
    var t = String(s || '').toLowerCase().replace(/&/g, ' and ').replace(/[^a-z0-9]+/g, ' ').trim().split(/\s+/);
    var out = [];
    t.forEach(function (w) { if (w && !STOP[w]) out.push(w); });
    return out;
  }

  // ------------------------------------------------------------------ data indexes
  var LOOK = {};      // normKey -> [cc, ccy, sector, displayName]
  var STOCK_BY_TICK = {}, STOCK_BY_CORE = {};
  function buildIndexes() {
    XR.stocks.forEach(function (r) {
      var name = r[0], ticks = r[1], cc = r[2], ccy = r[3], sec = r[4];
      LOOK[normKey(name)] = [cc, ccy, sec, name];
      ticks.forEach(function (t) { STOCK_BY_TICK[t.toUpperCase()] = name; });
      STOCK_BY_CORE[coreKey(name)] = name;
    });
    Object.keys(XR.look).forEach(function (name) {
      var r = XR.look[name]; var k = normKey(name);
      if (!LOOK[k]) LOOK[k] = [r[0], r[1], r[2], name];
      if (!STOCK_BY_CORE[coreKey(name)]) STOCK_BY_CORE[coreKey(name)] = name;
    });
    Object.keys(XR.india).forEach(function (name) {
      var k = normKey(name);
      if (!LOOK[k]) LOOK[k] = ['IN', 'INR', XR.india[name], name];
      if (!STOCK_BY_CORE[coreKey(name)]) STOCK_BY_CORE[coreKey(name)] = name;
    });
    Object.keys(XR.aliases).forEach(function (sym) { STOCK_BY_TICK[sym.toUpperCase()] = XR.aliases[sym]; });
  }
  function infoOf(name) {
    var r = LOOK[normKey(name)];
    if (r) return { cc: r[0], ccy: r[1], sector: r[2] || 'Unclassified' };
    return { cc: '??', ccy: '', sector: 'Unclassified' };
  }

  // ------------------------------------------------------------------ matching
  var TICK_TO_SCHEME = {}, ALIAS_SET = {};
  function indexSchemes(list) {
    SCHEMES = list.map(function (s) {
      var ticks = [];
      var all = s.name.match(/\(([A-Za-z0-9\/ ]+)\)/g), m = all && /\(([A-Za-z0-9\/ ]+)\)/.exec(all[all.length - 1]);
      if (m && /ETF|NSE-listed|US-listed|UCITS/.test(s.name)) m[1].split('/').forEach(function (t) { t = t.trim().toUpperCase(); if (t) { ticks.push(t); TICK_TO_SCHEME[t] = s.id; } });
      return { id: s.id, name: s.name, amc: s.amc, category: s.category, ticks: ticks, toks: toks(s.name), tokset: null };
    });
    SCHEMES.forEach(function (s) { s.tokset = {}; s.toks.forEach(function (t) { s.tokset[t] = 1; }); });
    Object.keys(XR.etfAlias || {}).forEach(function (t) { if (!TICK_TO_SCHEME[t.toUpperCase()] && schemeById(XR.etfAlias[t])) { TICK_TO_SCHEME[t.toUpperCase()] = XR.etfAlias[t]; ALIAS_SET[t.toUpperCase()] = 1; } });
  }
  function schemeById(id) { for (var i = 0; i < SCHEMES.length; i++) if (SCHEMES[i].id === id) return SCHEMES[i]; return null; }

  function bestFunds(raw) {
    var q = toks(raw);
    if (!q.length) return [];
    var out = [];
    SCHEMES.forEach(function (s) {
      var hit = 0; q.forEach(function (t) { if (s.tokset[t]) hit++; });
      if (!hit) return;
      var cover = hit / q.length, prec = hit / Math.max(1, s.toks.length);
      out.push({ s: s, score: cover * 0.8 + prec * 0.2, cover: cover });
    });
    out.sort(function (a, b) { return b.score - a.score; });
    return out.slice(0, 4);
  }

  var NONEQ_NAME = /\b(gold|silver|liquid|overnight|gilt|g-?sec|bonds?|debt|money market|treasury|fixed maturity|sdl|t-?bills?|fixed deposit|fd)\b/i;
  function matchOne(rawIn) {
    var raw = String(rawIn || '').trim();
    var clean = raw.replace(/^(NSE|BSE|NASDAQ|NYSE)\s*[:\-]\s*/i, '').replace(/[.\-](NS|BO|US|L|DE|AS|PA)$/i, '').replace(/-EQ$/i, '').trim();
    var sym = clean.toUpperCase().replace(/\s+/g, '');
    var looksSymbol = /^[A-Z0-9&\-.]{1,15}$/.test(clean.replace(/\s+/g, '')) && !/\s/.test(clean);
    if ((XR.nonEq || []).indexOf(sym) >= 0 || (NONEQ_NAME.test(clean) && !TICK_TO_SCHEME[sym])) return { kind: 'other' };
    // 1) exact ETF or stock ticker
    if (looksSymbol || clean.length <= 12) {
      if (TICK_TO_SCHEME[sym] != null) return { kind: 'fund', id: TICK_TO_SCHEME[sym], alias: !!ALIAS_SET[sym] };
      if (STOCK_BY_TICK[sym]) return { kind: 'stock', stock: STOCK_BY_TICK[sym] };
    }
    // 2) company name
    var core = coreKey(clean), stockHit = core && STOCK_BY_CORE[core];
    var fundish = /\b(fund|etf|index|fof|plan|scheme|nifty|sensex|elss|flexi|cap)\b/i.test(clean);
    var funds = bestFunds(clean);
    var top = funds[0];
    var okFund = top && top.cover >= 0.8 && (funds.length < 2 || top.score - funds[1].score >= 0.05 || top.score >= 0.95);
    if (stockHit && !(fundish && okFund)) return { kind: 'stock', stock: stockHit };
    if (okFund) return { kind: 'fund', id: top.s.id };
    var cands = funds.filter(function (f) { return f.cover >= 0.5; }).map(function (f) { return f.s.id; });
    return { kind: 'none', cands: cands };
  }

  // ------------------------------------------------------------------ CSV / paste parsing
  function splitLine(line, d) {
    var out = [], cur = '', q = false;
    for (var i = 0; i < line.length; i++) {
      var c = line[i];
      if (q) { if (c === '"') { if (line[i + 1] === '"') { cur += '"'; i++; } else q = false; } else cur += c; }
      else if (c === '"') q = true;
      else if (c === d) { out.push(cur); cur = ''; }
      else cur += c;
    }
    out.push(cur);
    return out.map(function (x) { return x.trim(); });
  }
  function num(s) {
    if (s == null) return NaN;
    var t = String(s).replace(/[₹$,\s]|rs\.?|inr|usd/gi, '').replace(/^\((.*)\)$/, '-$1');
    if (t === '' || !/^-?[0-9]*\.?[0-9]+$/.test(t)) return NaN;
    return parseFloat(t);
  }
  var NAME_H = /^(instrument|symbol|ticker|scheme( name)?|name|security( name)?|fund( name)?|holding|stock( name)?|company|asset|etf)$/i;
  var VAL_H = [/current value|present value|market value|current amount|latest value|value at|cur\.? val|closing value|closing amount|valuation/i, /^(value|amount|total value|market val)$/i];
  var INV_H = /invested|cost value|buy value|purchase value|buy amount/i;
  var QTY_H = /^(qty\.?|quantity|units|shares|balance units|closing balance units?)$/i;
  var PRICE_H = /^(ltp|price|nav|last price|close price|closing price|current price|market price|current nav)$/i;

  function parseText(text) {
    var lines = String(text || '').replace(/\r/g, '').split('\n').filter(function (l) { return l.trim() !== ''; });
    if (!lines.length) return [];
    var first = lines[0], d = ',';
    var counts = { ',': 0, '\t': 0, ';': 0 };
    lines.slice(0, 5).forEach(function (l) { Object.keys(counts).forEach(function (k) { counts[k] += l.split(k).length - 1; }); });
    d = counts['\t'] > counts[','] && counts['\t'] >= counts[';'] ? '\t' : (counts[';'] > counts[','] ? ';' : ',');
    var rows = lines.map(function (l) { return splitLine(l, d); });
    // header detection
    var hdrIdx = -1, nameC = -1, valC = -1, qtyC = -1, priceC = -1, invC = -1;
    for (var i = 0; i < Math.min(rows.length, 12); i++) {
      var r = rows[i], n = -1;
      r.forEach(function (c, j) { if (n < 0 && NAME_H.test(c.trim())) n = j; });
      if (n >= 0 && r.length >= 2) { hdrIdx = i; nameC = n; break; }
    }
    var out = [];
    if (hdrIdx >= 0) {
      var hdr = rows[hdrIdx];
      for (var p = 0; p < VAL_H.length && valC < 0; p++) hdr.forEach(function (c, j) { if (valC < 0 && VAL_H[p].test(c)) valC = j; });
      hdr.forEach(function (c, j) { if (qtyC < 0 && QTY_H.test(c.trim())) qtyC = j; if (priceC < 0 && PRICE_H.test(c.trim())) priceC = j; if (invC < 0 && INV_H.test(c)) invC = j; });
      rows.slice(hdrIdx + 1).forEach(function (r) {
        var name = r[nameC]; if (!name || /^(total|grand total)/i.test(name)) return;
        var amt = valC >= 0 ? num(r[valC]) : NaN;
        if (!isFinite(amt) && qtyC >= 0 && priceC >= 0) { var q = num(r[qtyC]), pr = num(r[priceC]); if (isFinite(q) && isFinite(pr)) amt = q * pr; }
        if (!isFinite(amt) && invC >= 0) amt = num(r[invC]);
        out.push({ raw: name, amount: isFinite(amt) ? amt : null });
      });
    } else {
      // free text: "VOO 250000", "Parag Parikh Flexi Cap, 2,00,000", "NVDA - $1,500"
      lines.forEach(function (line) {
        line = line.trim();
        var m = /^(.*?)[\s:=\-–,]+(?:rs\.?\s*|inr\s*|₹\s*|\$\s*|usd\s*)?([0-9][0-9,]*(?:\.[0-9]+)?)\s*(?:rs\.?|inr|usd|₹|\$|k|l|lakh|lakhs|cr)?\s*$/i.exec(line);
        if (m && m[1].trim()) {
          var v = num(m[2]); var tail = /(k|lakhs?|l|cr)\s*$/i.exec(line);
          if (tail) { var u = tail[1].toLowerCase(); v *= (u === 'k' ? 1e3 : (u === 'cr' ? 1e7 : 1e5)); }
          out.push({ raw: m[1].replace(/[,:\-]+$/, '').trim(), amount: v });
        } else out.push({ raw: line, amount: null });
      });
    }
    return out;
  }

  // ------------------------------------------------------------------ positions UI
  function addPos(raw, amount, forced) {
    var m = forced || matchOne(raw);
    var p = { uid: ++uidN, raw: raw, amount: amount, kind: m.kind, id: m.id, stock: m.stock, cands: m.cands || [], alias: !!m.alias };
    positions.push(p);
    return p;
  }
  function labelOf(p) {
    if (p.kind === 'fund') { var s = schemeById(p.id); return s ? s.name : 'Fund ' + p.id; }
    if (p.kind === 'stock') return p.stock;
    if (p.kind === 'other') return p.raw;
    return '';
  }
  function save() { try { localStorage.setItem(STORE, JSON.stringify({ positions: positions, ccy: entryCcy(), fx: $('xrFx').value })); } catch (e) { } }
  function load() {
    try {
      var d = JSON.parse(localStorage.getItem(STORE) || 'null');
      if (d && d.positions && d.positions.length) { positions = d.positions; uidN = positions.reduce(function (m, p) { return Math.max(m, p.uid || 0); }, 0); if (d.ccy) $('xrCcy').value = d.ccy; if (d.fx) $('xrFx').value = d.fx; return true; }
    } catch (e) { }
    return false;
  }

  function candSelect(p) {
    var opts = '<option value="">Pick the right fund or stock...</option>';
    (p.cands || []).forEach(function (id) { var s = schemeById(id); if (s) opts += '<option value="f:' + id + '">' + esc(s.name) + '</option>'; });
    opts += '<option value="skip">Leave this one out</option>';
    return '<select data-uid="' + p.uid + '" class="xr-pick w-full text-sm border border-amber-300 bg-amber-50 rounded-lg px-2 py-1.5">' + opts + '</select>';
  }

  function renderPositions() {
    var box = $('xrRows');
    if (!positions.length) { box.innerHTML = '<p class="text-sm text-slate-500 px-1 py-4">Nothing added yet. Upload a file, paste a list, search below, or try the sample portfolio.</p>'; $('xrTotals').textContent = ''; $('xrRun').disabled = true; save(); return; }
    var html = '';
    positions.forEach(function (p) {
      var chip, label = labelOf(p);
      if (p.kind === 'fund') chip = '<span class="text-xs font-semibold text-emerald-700 bg-emerald-50 border border-emerald-200 rounded-full px-2 py-0.5 whitespace-nowrap">Fund or ETF</span>';
      else if (p.kind === 'stock') chip = '<span class="text-xs font-semibold text-indigo-700 bg-indigo-50 border border-indigo-200 rounded-full px-2 py-0.5 whitespace-nowrap">Direct stock</span>';
      else if (p.kind === 'other') chip = '<span class="text-xs font-semibold text-slate-600 bg-slate-100 border border-slate-200 rounded-full px-2 py-0.5 whitespace-nowrap">Gold, debt or cash</span>';
      else chip = '<span class="text-xs font-semibold text-amber-800 bg-amber-50 border border-amber-200 rounded-full px-2 py-0.5 whitespace-nowrap">Not matched</span>';
      var main = p.kind === 'none'
        ? '<div class="text-sm text-slate-700 mb-1.5">' + esc(p.raw) + '</div>' + candSelect(p)
        : '<div class="text-sm font-semibold text-slate-900 break-words">' + esc(label) + '</div>' + (norm(p.raw) !== norm(label) ? '<div class="text-xs text-slate-400 break-words">from "' + esc(p.raw) + '"' + (p.alias ? ': another fund house\'s ETF on the same index, so the same companies' : '') + '</div>' : '');
      var amt = p.amount == null ? '' : p.amount;
      html += '<div class="grid grid-cols-[1fr_auto] sm:grid-cols-[auto_1fr_150px_auto] gap-x-3 gap-y-2 items-center border-t border-slate-100 py-3">' +
        '<div class="order-1">' + chip + '</div>' +
        '<div class="order-3 sm:order-2 col-span-2 sm:col-span-1">' + main + '</div>' +
        '<div class="order-2 sm:order-3"><input data-uid="' + p.uid + '" class="xr-amt w-full sm:w-36 text-sm border border-slate-200 rounded-lg px-2.5 py-1.5 text-right" inputmode="decimal" placeholder="Amount" aria-label="Amount for ' + esc(label || p.raw) + '" value="' + esc(amt) + '"></div>' +
        '<div class="order-2 sm:order-4 text-right"><button data-uid="' + p.uid + '" class="xr-del text-xs text-slate-400 hover:text-red-600" aria-label="Remove">Remove</button></div>' +
        '</div>';
    });
    box.innerHTML = html;
    updateTotals();
    save();
  }
  function norm(s) { return String(s || '').toLowerCase().replace(/[^a-z0-9]/g, ''); }
  function amountInr(p) {
    var a = parseFloat(p.amount);
    if (!isFinite(a) || a <= 0) return 0;
    return entryCcy() === 'USD' ? a * fx() : a;
  }
  function updateTotals() {
    var usable = positions.filter(function (p) { return p.kind !== 'none' && amountInr(p) > 0; });
    var tot = positions.reduce(function (s, p) { return s + (p.kind === 'none' ? 0 : amountInr(p)); }, 0);
    var nomatch = positions.filter(function (p) { return p.kind === 'none'; }).length;
    var noamt = positions.filter(function (p) { return p.kind !== 'none' && !(amountInr(p) > 0); }).length;
    var msg = positions.length + ' rows, total ' + inr(tot);
    if (nomatch) msg += ' · ' + nomatch + ' not matched yet';
    if (noamt) msg += ' · ' + noamt + ' without an amount';
    $('xrTotals').textContent = msg;
    $('xrRun').disabled = usable.length < 1;
  }

  // ------------------------------------------------------------------ import actions
  function ingest(rows, method) {
    var added = 0, unmatched = 0;
    rows.forEach(function (r) {
      if (!r.raw) return;
      var p = addPos(r.raw, r.amount);
      added++; if (p.kind === 'none') unmatched++;
    });
    renderPositions();
    track('xray_import', { method: method, rows: added, unmatched: unmatched });
    var st = $('xrImportStatus');
    st.className = 'text-xs mt-2 ' + (added ? 'text-emerald-700' : 'text-red-600');
    st.textContent = added ? ('Added ' + added + ' row' + (added > 1 ? 's' : '') + (unmatched ? ', ' + unmatched + ' need a quick fix below.' : ', all recognised.')) : 'We could not find any rows. Check the file has a name column and an amount column, or paste one holding per line.';
  }

  // ------------------------------------------------------------------ holdings fetch
  function fetchHoldings(id) {
    if (holdingsCache[id]) return Promise.resolve(holdingsCache[id]);
    return fetch('/api/holdings/' + id).then(function (r) { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); }).then(function (d) {
      var rows = (d.equity_holdings || []).map(function (h) { return { name: h.stock_name, w: parseFloat(h.weight_pct) || 0 }; });
      var sum = rows.reduce(function (s, h) { return s + h.w; }, 0);
      if (sum > 100.5) rows.forEach(function (h) { h.w = h.w * 100 / sum; });
      holdingsCache[id] = { rows: rows, month: d.month };
      return holdingsCache[id];
    });
  }

  // ------------------------------------------------------------------ the X-ray
  function estateTax(v) {
    var x = 0, lo = 0;
    for (var i = 0; i < BRACKETS.length; i++) { var hi = BRACKETS[i][0], r = BRACKETS[i][1]; if (v > lo) x += (Math.min(v, hi) - lo) * r; lo = hi; }
    return Math.max(0, x - 13000);
  }

  function run() {
    var items = positions.filter(function (p) { return p.kind !== 'none' && amountInr(p) > 0; });
    if (!items.length) return;
    var btn = $('xrRun'); btn.disabled = true; var orig = btn.textContent; btn.textContent = 'Looking inside your funds...';
    var ids = {}; items.forEach(function (p) { if (p.kind === 'fund') ids[p.id] = 1; });
    Promise.all(Object.keys(ids).map(function (id) { return fetchHoldings(parseInt(id, 10)).then(function () { return null; }, function (e) { return +id; }); })).then(function (failed) {
      failed = failed.filter(function (x) { return x != null; });
      var res = compute(items, failed);
      lastResult = res; render(res);
      track('xray_run', { positions: items.length, funds: Object.keys(ids).length, visible_pct: Math.round(res.visiblePct), unmatched: positions.filter(function (p) { return p.kind === 'none'; }).length });
      btn.textContent = orig; btn.disabled = false;
      var el = $('xrResults'); el.classList.remove('hidden'); el.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
  }

  function compute(items, failed) {
    var total = 0; items.forEach(function (p) { total += amountInr(p); });
    var exp = {};   // key -> {name, amt, holders:{uid:amt}, direct}
    var spell = {};
    var visibleAmt = 0, perPos = [];
    items.forEach(function (p) {
      var A = amountInr(p), vis = 0, label = labelOf(p);
      if (p.kind === 'other') {
        perPos.push({ p: p, A: A, vis: 0, label: label, other: true }); return;
      } else if (p.kind === 'stock') {
        add(p.stock, A, p, true); vis = A;
      } else {
        var h = holdingsCache[p.id];
        if (!h) { perPos.push({ p: p, A: A, vis: 0, label: label, failed: true }); return; }
        h.rows.forEach(function (r) {
          if (r.name.indexOf(NOT_ITEMISED) >= 0) return;
          var a = A * r.w / 100; vis += a; add(r.name, a, p, false);
        });
      }
      visibleAmt += vis;
      perPos.push({ p: p, A: A, vis: vis, label: label, month: p.kind === 'fund' ? (holdingsCache[p.id] || {}).month : null });
    });
    function add(name, a, p, direct) {
      var k = normKey(name).replace(/class[a-z]$/, '');   // Alphabet Class A and C are one company
      var e = exp[k] || (exp[k] = { key: k, name: name, amt: 0, holders: {}, direct: false, spells: {} });
      e.amt += a; e.holders[p.uid] = (e.holders[p.uid] || 0) + a; if (direct) e.direct = true;
      e.spells[name] = (e.spells[name] || 0) + 1;
    }
    var list = Object.keys(exp).map(function (k) {
      var e = exp[k]; var best = e.name, bc = 0; Object.keys(e.spells).forEach(function (s) { if (e.spells[s] > bc) { bc = e.spells[s]; best = s; } });
      var inf = infoOf(best);
      if (Object.keys(e.spells).length > 1 && / Class [A-Z]$/.test(best)) best = best.replace(/ Class [A-Z]$/, '');
      e.name = best; e.via = Object.keys(e.holders).length; e.cc = inf.cc; e.sector = inf.sector; return e;
    }).sort(function (a, b) { return b.amt - a.amt; });

    var byCc = {}, bySec = {};
    list.forEach(function (e) { byCc[e.cc] = (byCc[e.cc] || 0) + e.amt; bySec[e.sector] = (bySec[e.sector] || 0) + e.amt; });

    // overlap between fund positions (same method as the analyzer: weights scaled to 100 on the listed holdings, smaller weight of each shared company)
    var funds = items.filter(function (p) { return p.kind === 'fund' && holdingsCache[p.id]; });
    var pairs = [];
    for (var i = 0; i < funds.length; i++) for (var j = i + 1; j < funds.length; j++) {
      if (funds[i].id === funds[j].id) continue;
      var A = scaled(funds[i].id), B = scaled(funds[j].id), o = 0;
      Object.keys(A).forEach(function (k) { if (B[k] != null) o += Math.min(A[k], B[k]); });
      pairs.push({ a: labelOf(funds[i]), b: labelOf(funds[j]), o: o });
    }
    pairs.sort(function (a, b) { return b.o - a.o; });

    // estate: US-situs assets = US-listed ETFs (full value) + direct shares of US-incorporated companies
    var us = 0, usParts = [];
    items.forEach(function (p) {
      var A = amountInr(p);
      if (p.kind === 'fund') { var s = schemeById(p.id); if (s && /US-listed/.test(s.name)) { us += A; usParts.push({ label: s.name.replace(/ - US-listed$/, ''), A: A }); } }
      else if (p.kind === 'stock' && infoOf(p.stock).cc === 'US') { us += A; usParts.push({ label: p.stock, A: A }); }
    });
    var usd = us / fx();
    return { total: total, items: items, perPos: perPos, list: list, byCc: byCc, bySec: bySec, visibleAmt: visibleAmt, visiblePct: total ? visibleAmt / total * 100 : 0, pairs: pairs, us: us, usd: usd, usParts: usParts, failed: failed, tax: estateTax(usd) };
    function scaled(id) {
      var rows = holdingsCache[id].rows;   // includes each ETF's unique "not itemised" bucket, exactly like the analyzer, so overlap is never inflated
      var s = rows.reduce(function (t, r) { return t + r.w; }, 0), o = {};
      rows.forEach(function (r) { var k = normKey(r.name); o[k] = (o[k] || 0) + (s ? r.w / s * 100 : 0); });
      return o;
    }
  }

  var CC_NAMES = { IN: 'India', US: 'United States', '??': 'Not classified' };
  function ccName(c) { return CC_NAMES[c] || (XR.countries[c] || c); }

  function bars(rows, total, color, fmt) {
    return rows.map(function (r) {
      var w = total ? Math.max(0.6, r.v / total * 100) : 0;
      return '<div class="mb-2.5"><div class="flex justify-between gap-3 text-sm"><span class="text-slate-800 break-words min-w-0">' + r.label + '</span><span class="font-semibold text-slate-900 whitespace-nowrap">' + (fmt ? fmt(r) : '') + '</span></div>' +
        '<div class="h-2 rounded-full bg-slate-100 mt-1" role="img" aria-label="' + esc(r.plain || '') + '"><div class="h-2 rounded-full ' + color + '" style="width:' + w.toFixed(1) + '%"></div></div>' + (r.sub ? '<div class="text-xs text-slate-500 mt-0.5">' + r.sub + '</div>' : '') + '</div>';
    }).join('');
  }

  function render(R) {
    var T = R.total, out = '';
    var top10 = R.list.slice(0, 10).reduce(function (s, e) { return s + e.amt; }, 0);
    var topE = R.list[0];
    var dup = R.list.filter(function (e) { return e.via >= 3; });
    var dupAmt = dup.reduce(function (s, e) { return s + e.amt; }, 0);

    // headline
    var heads = [];
    heads.push('<div class="rounded-2xl bg-gradient-to-br from-indigo-600 to-violet-600 text-white p-5 sm:p-7">' +
      '<p class="text-xs font-semibold tracking-wide text-indigo-100">YOUR X-RAY</p>' +
      '<p class="text-xl sm:text-2xl font-bold mt-1 leading-snug">' + R.items.length + ' holding' + (R.items.length > 1 ? 's' : '') + ', ' + inr(T) + ' in total.' +
      (topE ? ' The single biggest company underneath is <span class="underline decoration-white/40">' + esc(topE.name) + '</span> at ' + pct(topE.amt / T * 100) + ' of everything you own.' : '') + '</p>' +
      '<div class="grid grid-cols-3 gap-3 mt-5 text-center">' +
      '<div class="bg-white/15 rounded-xl p-3"><div class="text-lg sm:text-2xl font-bold">' + pct(top10 / T * 100, 0) + '</div><div class="text-[11px] sm:text-xs text-indigo-100">in your top 10 companies</div></div>' +
      '<div class="bg-white/15 rounded-xl p-3"><div class="text-lg sm:text-2xl font-bold">' + dup.length + '</div><div class="text-[11px] sm:text-xs text-indigo-100">companies reached through 3+ holdings</div></div>' +
      '<div class="bg-white/15 rounded-xl p-3"><div class="text-lg sm:text-2xl font-bold">' + pct(R.visiblePct, 0) + '</div><div class="text-[11px] sm:text-xs text-indigo-100">of your money we can see by company</div></div>' +
      '</div></div>');

    // top companies
    var rows = R.list.slice(0, 15).map(function (e) {
      var holders = Object.keys(e.holders).map(function (u) { var p = positions.filter(function (q) { return q.uid === +u; })[0]; return p ? labelOf(p) : ''; }).filter(Boolean);
      var sub = e.direct && e.via === 1 ? 'Held directly' : ('Reached through ' + e.via + ' of your holdings' + (e.direct ? ' (including directly)' : ''));
      return { label: esc(e.name) + ' <span class="text-xs text-slate-400">' + esc(ccName(e.cc)) + '</span>', v: e.amt, sub: sub + (e.via >= 2 ? ': ' + esc(holders.slice(0, 4).join(', ') + (holders.length > 4 ? ' and ' + (holders.length - 4) + ' more' : '')) : ''), plain: e.name + ' ' + pct(e.amt / T * 100) };
    });
    heads.push(card('What you really own: your top 15 companies', 'Added up across every fund, ETF and direct stock. Percent of your whole portfolio, rupee value alongside.',
      bars(rows, R.list[0] ? R.list[0].amt : 1, 'bg-gradient-to-r from-indigo-500 to-violet-500', function (r) { return pct(r.v / T * 100, 1) + ' <span class="text-xs font-normal text-slate-500">' + inr(r.v) + '</span>'; })));

    // duplicates
    if (dup.length) {
      heads.push(card('Hidden duplicates', 'You may think you own ' + R.items.length + ' different things. These companies show up again and again.',
        '<p class="text-sm text-slate-700 mb-3">' + dup.length + ' compan' + (dup.length > 1 ? 'ies are' : 'y is') + ' reached through three or more of your holdings and together make up <strong>' + pct(dupAmt / T * 100) + '</strong> of your portfolio.</p>' +
        '<ul class="text-sm text-slate-700 space-y-1">' + dup.slice(0, 6).map(function (e) { return '<li><strong>' + esc(e.name) + '</strong>: in ' + e.via + ' holdings, ' + pct(e.amt / T * 100) + ' of your money</li>'; }).join('') + '</ul>'));
    }

    // country + sector
    var cRows = Object.keys(R.byCc).map(function (c) { return { label: esc(ccName(c)), v: R.byCc[c], plain: ccName(c) }; }).sort(function (a, b) { return b.v - a.v; });
    var cTot = cRows.reduce(function (s, r) { return s + r.v; }, 0);
    var sRows = Object.keys(R.bySec).map(function (c) { return { label: esc(c), v: R.bySec[c], plain: c }; }).sort(function (a, b) { return b.v - a.v; });
    var cc = '<p class="text-xs text-slate-500 mb-3">Based on the ' + pct(R.visiblePct, 0) + ' of your money we can see at company level. Funds publish long lists, we hold the biggest holdings.</p>';
    heads.push('<div class="grid md:grid-cols-2 gap-5">' +
      card('Where in the world', 'Home country of each company, not where the fund or ETF is listed.', cc + bars(cRows.slice(0, 8), cTot, 'bg-gradient-to-r from-sky-500 to-indigo-500', function (r) { return pct(r.v / cTot * 100, 0); })) +
      card('Which sectors', 'Simplified sector groups assigned by us.', cc + bars(sRows.slice(0, 9), cTot, 'bg-gradient-to-r from-emerald-500 to-teal-500', function (r) { return pct(r.v / cTot * 100, 0); })) + '</div>');

    // overlap pairs
    if (R.pairs.length) {
      var pr = R.pairs.slice(0, 6).map(function (p) { return '<tr class="border-t border-slate-100"><td class="py-2 pr-3 text-slate-800">' + esc(p.a) + '<span class="text-slate-400"> and </span>' + esc(p.b) + '</td><td class="py-2 text-right font-semibold whitespace-nowrap ' + (p.o >= 50 ? 'text-red-600' : (p.o >= 25 ? 'text-amber-600' : 'text-emerald-600')) + '">at least ' + pct(p.o, 0) + '</td></tr>'; }).join('');
      heads.push(card('Which of your holdings look most alike', 'Overlap is measured on each fund\'s listed top holdings (the same method as our analyzer), so the real figure can only be higher.',
        '<table class="w-full text-sm"><tbody>' + pr + '</tbody></table><p class="text-xs text-slate-500 mt-3"><a href="/" class="text-indigo-600 underline">Open the full overlap analyzer</a> to see which companies they share.</p>'));
    }

    // estate
    var ratio = R.usd / USD_THRESHOLD, eTone = ratio >= 1 ? 'border-red-200 bg-red-50' : (ratio >= 0.5 ? 'border-amber-200 bg-amber-50' : 'border-emerald-200 bg-emerald-50');
    var eMsg;
    if (R.us <= 0) eMsg = 'You hold no US-listed ETFs or direct US stocks, so the US estate-tax rule does not apply to what you entered.';
    else if (ratio >= 1) eMsg = 'US-situs assets of about <strong>USD ' + Math.round(R.usd).toLocaleString('en-US') + '</strong> are above the USD 60,000 line. If you died holding them, a US estate-tax return could be required, and a rough tax of about <strong>USD ' + Math.round(R.tax).toLocaleString('en-US') + '</strong> could apply. Irish UCITS ETFs and Indian funds are the usual ways to stay out of this.';
    else if (ratio >= 0.5) eMsg = 'US-situs assets are about <strong>USD ' + Math.round(R.usd).toLocaleString('en-US') + '</strong>, over half of the USD 60,000 line. Growth or new buying could take you over it.';
    else eMsg = 'US-situs assets are about <strong>USD ' + Math.round(R.usd).toLocaleString('en-US') + '</strong>, well under the USD 60,000 line. No estate-tax return would be needed today.';
    heads.push('<div class="rounded-2xl border ' + eTone + ' p-5 sm:p-6"><h3 class="text-base sm:text-lg font-bold text-slate-900">US estate-tax check</h3>' +
      '<p class="text-sm text-slate-700 mt-2">' + eMsg + '</p>' +
      (R.usParts.length ? '<p class="text-xs text-slate-600 mt-3">Counted as US assets: ' + R.usParts.map(function (u) { return esc(u.label) + ' (' + inr(u.A) + ')'; }).join('; ') + '. Using USD 1 = ' + inr(fx()).replace('₹', '₹') + '. Not counted: Indian mutual funds, Irish UCITS ETFs, and shares of non-US companies.</p>' : '') +
      '<p class="text-xs text-slate-500 mt-2">Education only, not tax advice. <a class="text-indigo-600 underline" href="/blog/us-estate-tax-indians-us-stocks-etfs">How the rule works</a> and <a class="text-indigo-600 underline" href="/blog/international-etfs-india-us-listed-vs-ucits#calc">the fee-versus-estate-tax calculator</a>.</p></div>');

    // per-holding coverage
    var cov = R.perPos.map(function (x) {
      var v = x.A ? x.vis / x.A * 100 : 0;
      return '<tr class="border-t border-slate-100"><td class="py-2 pr-3 text-slate-800 break-words">' + esc(x.label) + (x.failed ? ' <span class="text-xs text-red-600">(holdings not available)</span>' : '') + (x.other ? ' <span class="text-xs text-slate-400">(gold, debt or cash: no companies to look inside)</span>' : '') + '</td><td class="py-2 pr-3 text-right whitespace-nowrap">' + inr(x.A) + '</td><td class="py-2 text-right whitespace-nowrap ' + (v < 40 ? 'text-amber-700' : 'text-slate-700') + '">' + (x.other ? 'n/a' : pct(v, 0)) + '</td></tr>';
    }).join('');
    heads.push(card('How much of each holding we can see', 'Funds publish many holdings but we hold each fund\'s biggest ones. A low number just means a spread-out fund (such as a small cap or a world ETF), so its smaller positions are not counted above.',
      '<div class="overflow-x-auto"><table class="w-full text-sm"><thead><tr class="text-left text-xs text-slate-400"><th class="py-1 pr-3">Holding</th><th class="py-1 pr-3 text-right">Your amount</th><th class="py-1 text-right">Seen by company</th></tr></thead><tbody>' + cov + '</tbody></table></div>'));

    var unm = positions.filter(function (p) { return p.kind === 'none'; });
    if (unm.length) heads.push('<div class="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">' + unm.length + ' row' + (unm.length > 1 ? 's were' : ' was') + ' left out because we could not match ' + (unm.length > 1 ? 'them' : 'it') + ': ' + esc(unm.map(function (p) { return p.raw; }).slice(0, 6).join(', ')) + '. Pick the right fund in the list above and run the X-ray again.</div>');

    heads.push('<div class="flex flex-wrap gap-3 pt-1"><button id="xrCsv" class="px-4 py-2.5 rounded-xl border border-slate-300 bg-white text-sm font-semibold text-slate-700 hover:bg-slate-50">Download company list (CSV)</button>' +
      '<a href="/" class="px-4 py-2.5 rounded-xl bg-gradient-to-r from-indigo-600 to-violet-600 text-white text-sm font-semibold hover:shadow-lg">Compare these funds in the analyzer</a></div>' +
      '<p class="text-xs text-slate-400">Educational view of public holdings data, not advice to buy, sell or hold anything. Holdings are the latest we have (dated in the analyzer) and change every month.</p>');

    $('xrOut').innerHTML = heads.join('<div class="h-5"></div>');
    var b = $('xrCsv'); if (b) b.addEventListener('click', downloadCsv);
  }
  function card(title, sub, body) { return '<div class="rounded-2xl bg-white border border-slate-200 p-5 sm:p-6"><h3 class="text-base sm:text-lg font-bold text-slate-900">' + title + '</h3><p class="text-xs sm:text-sm text-slate-500 mt-1 mb-4">' + sub + '</p>' + body + '</div>'; }

  function downloadCsv() {
    if (!lastResult) return;
    var T = lastResult.total, rows = [['Company', 'Country', 'Sector', 'Value (INR)', 'Percent of portfolio', 'Reached through holdings']];
    lastResult.list.forEach(function (e) { rows.push([e.name, ccName(e.cc), e.sector, Math.round(e.amt), (e.amt / T * 100).toFixed(2), e.via]); });
    var csv = rows.map(function (r) { return r.map(function (c) { c = String(c); return /[",\n]/.test(c) ? '"' + c.replace(/"/g, '""') + '"' : c; }).join(','); }).join('\n');
    var a = document.createElement('a'); a.href = URL.createObjectURL(new Blob([csv], { type: 'text/csv' })); a.download = 'overlapiq-xray.csv'; document.body.appendChild(a); a.click(); a.remove();
    track('xray_export', { rows: lastResult.list.length });
  }

  // ------------------------------------------------------------------ manual search
  function searchLocal(q) {
    q = q.trim(); if (q.length < 2) return [];
    var ql = q.toLowerCase(), qt = toks(q), out = [];
    SCHEMES.forEach(function (s) {
      var hit = s.name.toLowerCase().indexOf(ql) >= 0 || s.ticks.some(function (t) { return t.toLowerCase() === ql; }) || (qt.length && qt.every(function (t) { return s.tokset[t]; }));
      if (hit) out.push({ kind: 'fund', id: s.id, label: s.name, sub: s.category + ' · ' + s.amc });
    });
    var seen = {};
    Object.keys(STOCK_BY_TICK).forEach(function (t) {
      var nm = STOCK_BY_TICK[t];
      if ((t.toLowerCase() === ql || nm.toLowerCase().indexOf(ql) >= 0) && !seen[nm]) { seen[nm] = 1; out.push({ kind: 'stock', stock: nm, label: nm, sub: 'Direct stock · ' + ccName(infoOf(nm).cc) }); }
    });
    return out.slice(0, 12);
  }

  // ------------------------------------------------------------------ sample
  var SAMPLE = 'Instrument,Current value\nParag Parikh Flexi Cap Fund Direct Growth,400000\nHDFC Nifty 50 Index Fund Direct Growth,300000\nAxis Bluechip Fund,200000\nMotilal Oswal Nasdaq 100 FoF,150000\nVOO,250000\nQQQ,150000\nSCHD,100000\nINDA,80000\nRELIANCE,120000\nHDFCBANK,100000\nNVDA,90000\n';

  // ------------------------------------------------------------------ wiring
  function wire() {
    $('xrFile').addEventListener('change', function (ev) {
      var f = ev.target.files && ev.target.files[0]; if (!f) return;
      if (/\.(xlsx|xls)$/i.test(f.name)) { var st = $('xrImportStatus'); st.className = 'text-xs mt-2 text-red-600'; st.textContent = 'Excel files cannot be read here. In Excel choose Save As, CSV, and upload that file.'; return; }
      var r = new FileReader(); r.onload = function () { ingest(parseText(String(r.result)), 'csv'); }; r.readAsText(f); ev.target.value = '';
    });
    $('xrPasteBtn').addEventListener('click', function () { var t = $('xrPaste').value; if (!t.trim()) return; ingest(parseText(t), 'paste'); $('xrPaste').value = ''; });
    $('xrSample').addEventListener('click', function () { positions = []; $('xrCcy').value = 'INR'; ingest(parseText(SAMPLE), 'sample'); });
    $('xrClear').addEventListener('click', function () { positions = []; lastResult = null; $('xrResults').classList.add('hidden'); $('xrImportStatus').textContent = ''; renderPositions(); try { localStorage.removeItem(STORE); } catch (e) { } });
    $('xrRun').addEventListener('click', run);
    $('xrCcy').addEventListener('change', function () { updateTotals(); save(); });
    $('xrFx').addEventListener('input', function () { updateTotals(); save(); });
    $('xrRows').addEventListener('input', function (ev) {
      var t = ev.target; if (!t.classList.contains('xr-amt')) return;
      var p = positions.filter(function (q) { return q.uid === +t.dataset.uid; })[0]; if (!p) return;
      var v = num(t.value); p.amount = isFinite(v) ? v : null; updateTotals(); save();
    });
    $('xrRows').addEventListener('change', function (ev) {
      var t = ev.target; if (!t.classList.contains('xr-pick')) return;
      var p = positions.filter(function (q) { return q.uid === +t.dataset.uid; })[0]; if (!p || !t.value) return;
      if (t.value === 'skip') { positions = positions.filter(function (q) { return q !== p; }); }
      else if (t.value.indexOf('f:') === 0) { p.kind = 'fund'; p.id = parseInt(t.value.slice(2), 10); }
      renderPositions();
    });
    $('xrRows').addEventListener('click', function (ev) {
      var t = ev.target; if (!t.classList.contains('xr-del')) return;
      positions = positions.filter(function (q) { return q.uid !== +t.dataset.uid; }); renderPositions();
    });
    var inp = $('xrSearch'), dd = $('xrDrop');
    inp.addEventListener('input', function () {
      var res = searchLocal(inp.value);
      if (!res.length) { dd.classList.add('hidden'); dd.innerHTML = ''; return; }
      dd.innerHTML = res.map(function (r, i) { return '<button type="button" data-i="' + i + '" class="w-full text-left px-3 py-2 hover:bg-indigo-50 border-b border-slate-100 last:border-0"><div class="text-sm font-semibold text-slate-900">' + esc(r.label) + '</div><div class="text-xs text-slate-500">' + esc(r.sub) + '</div></button>'; }).join('');
      dd.classList.remove('hidden'); dd._res = res;
    });
    dd.addEventListener('click', function (ev) {
      var b = ev.target.closest('button'); if (!b) return; var r = dd._res[+b.dataset.i];
      var p = addPos(r.label, null, r.kind === 'fund' ? { kind: 'fund', id: r.id } : { kind: 'stock', stock: r.stock });
      dd.classList.add('hidden'); inp.value = ''; renderPositions(); track('xray_import', { method: 'search', rows: 1, unmatched: 0 });
      var el = document.querySelector('.xr-amt[data-uid="' + p.uid + '"]'); if (el) el.focus();
    });
    document.addEventListener('click', function (ev) { if (!dd.contains(ev.target) && ev.target !== inp) dd.classList.add('hidden'); });
    var drop = $('xrDropzone');
    ['dragenter', 'dragover'].forEach(function (n) { drop.addEventListener(n, function (e) { e.preventDefault(); drop.classList.add('border-indigo-400', 'bg-indigo-50'); }); });
    ['dragleave', 'drop'].forEach(function (n) { drop.addEventListener(n, function (e) { e.preventDefault(); drop.classList.remove('border-indigo-400', 'bg-indigo-50'); }); });
    drop.addEventListener('drop', function (e) { var f = e.dataTransfer.files && e.dataTransfer.files[0]; if (!f) return; var r = new FileReader(); r.onload = function () { ingest(parseText(String(r.result)), 'csv'); }; r.readAsText(f); });
  }

  function start() {
    buildIndexes();
    wire();
    fetch('/api/xray/index').then(function (r) { return r.json(); }).then(function (list) {
      indexSchemes(list);
      var had = load();
      // re-match anything saved as unmatched, in case the index has loaded since
      positions.forEach(function (p) { if (p.kind === 'none') { var m = matchOne(p.raw); if (m.kind !== 'none') { p.kind = m.kind; p.id = m.id; p.stock = m.stock; } } });
      renderPositions();
      if (/[?&]sample=1\b/.test(location.search)) { $('xrSample').click(); }
      $('xrReady').classList.remove('hidden'); $('xrLoading').classList.add('hidden');
      window.__xrReady = true;
    }).catch(function () { $('xrLoading').textContent = 'Could not load the fund list. Please refresh the page.'; });
  }
  window.__xr = { matchOne: matchOne, parseText: parseText, normKey: normKey, compute: function () { return lastResult; } };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start); else start();
})();
