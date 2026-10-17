/* OverlapIQ Learn: Replay Lab. Virtual Rs 10 lakh, real Nifty 50 closing levels. All state stays in this browser. Education only. */
(function () {
  'use strict';
  var L = window.LAB, OIQ = window.OIQ;
  if (!L || !OIQ || !document.getElementById('labSetup')) return;
  var CASH0 = 1000000, COST = L.cost, GAP = 20, JKEY = 'overlapiq_journal_v1';
  var $ = function (id) { return document.getElementById(id); };
  var S = null, R = null, timer = null;

  // ---------------------------------------------------------------- pure engine
  function px(i) { return S.ep.closes[i]; }
  function N() { return S.ep.closes.length; }
  function mkDD(i) { return (S.mkPeak[i] - px(i)) / S.mkPeak[i] * 100; }
  function value(i) { return S.cash + S.units * px(i); }
  function newState(ep, blind) {
    var c = ep.closes;
    var mp = [], m = 0;
    for (var i = 0; i < c.length; i++) { m = Math.max(m, c[i]); mp.push(m); }
    return { ep: ep, blind: blind, i: 0, cash: CASH0, units: 0, trades: [], checks: [], costPaid: 0, vals: [CASH0], expo: [0], peak: CASH0, maxdd: 0,
      sip: { on: false, amt: 25000 }, mkPeak: mp, flagged: {}, nudge: null, finished: false };
  }
  function touch() {
    var v = value(S.i); S.vals[S.i] = v;
    S.expo[S.i] = v > 0 ? S.units * px(S.i) / v : 0;
    if (v > S.peak) S.peak = v;
    var dd = (S.peak - v) / S.peak * 100; if (dd > S.maxdd) S.maxdd = dd;
    return dd;
  }
  function buy(amount, reason, note, auto) {
    if (!S || S.finished) return null;
    amount = Math.min(+amount || 0, S.cash);
    if (!(amount >= 1)) return null;
    var fee = amount * COST, u = (amount - fee) / px(S.i);
    S.cash -= amount; S.units += u; S.costPaid += fee;
    var t = { day: S.i, type: 'buy', amt: amount, price: px(S.i), units: u, fee: fee, reason: reason || '', note: note || '', mkdd: mkDD(S.i), auto: !!auto };
    S.trades.push(t); touch(); return t;
  }
  function sell(frac, reason, note) {
    if (!S || S.finished) return null;
    frac = Math.max(0, Math.min(1, +frac || 0));
    var u = S.units * frac, gross = u * px(S.i);
    if (!(gross >= 1)) return null;
    var fee = gross * COST;
    S.cash += gross - fee; S.units -= u; S.costPaid += fee;
    var t = { day: S.i, type: 'sell', amt: gross, price: px(S.i), units: u, fee: fee, reason: reason || '', note: note || '', mkdd: mkDD(S.i), auto: false };
    S.trades.push(t); touch(); return t;
  }
  function step() {
    if (!S || S.finished || S.i >= N() - 1) return false;
    S.i++;
    if (S.sip.on && S.i % GAP === 0 && S.cash >= 1) buy(Math.min(S.cash, S.sip.amt), 'Auto-invest', '', true);
    var dd = touch();
    if (S.units > 0) {
      [10, 20, 30].forEach(function (t) { if (dd >= t && !S.flagged[t]) { S.flagged[t] = true; S.nudge = { t: t, dd: dd, day: S.i }; } });
    }
    return true;
  }
  function bench() {
    var n = N(), c = S.ep.closes, parts = Math.floor((n - 1) / GAP) + 1, part = CASH0 / parts;
    var bh = [], sp = [], u = 0, k = 0, ub = CASH0 * (1 - COST) / c[0];
    for (var i = 0; i < n; i++) {
      bh.push(ub * c[i]);
      if (i % GAP === 0 && k < parts) { u += part * (1 - COST) / c[i]; k++; }
      sp.push(u * c[i] + part * (parts - k));
    }
    return { bh: bh, sip: sp, cash: bh.map(function () { return CASH0; }), parts: parts };
  }
  function maxdd(a) { var p = 0, m = 0; a.forEach(function (v) { if (v > p) p = v; var d = (p - v) / p * 100; if (d > m) m = d; }); return m; }
  function finish() {
    if (!S || S.finished) return null;
    while (S.i < N() - 1) step();
    S.finished = true; S.nudge = null; stop();
    var b = bench(), n = N(), v = S.vals[n - 1], c = S.ep.closes;
    var mk = 0, pk = 0; c.forEach(function (x) { if (x > pk) pk = x; var d = (pk - x) / pk * 100; if (d > mk) mk = d; });
    var fearSells = S.trades.filter(function (t) { return t.type === 'sell' && t.mkdd >= 10; });
    var chase = S.trades.filter(function (t) { return t.type === 'buy' && !t.auto && t.day >= GAP && t.price / c[t.day - GAP] - 1 >= 0.08; });
    var avgExpo = S.expo.reduce(function (a, b2) { return a + b2; }, 0) / n * 100;
    R = { final: v, ret: (v / CASH0 - 1) * 100, bhFinal: b.bh[n - 1], bhRet: (b.bh[n - 1] / CASH0 - 1) * 100, sipFinal: b.sip[n - 1], sipRet: (b.sip[n - 1] / CASH0 - 1) * 100,
      maxdd: S.maxdd, bhDD: maxdd(b.bh), sipDD: maxdd(b.sip), mkDD: mk, trades: S.trades.length, cost: S.costPaid, fearSells: fearSells, chase: chase, avgExpo: avgExpo, b: b };
    return R;
  }

  // ---------------------------------------------------------------- charts (SVG)
  function lvl(i) { return S.blind ? S.ep.closes[i] / S.ep.closes[0] * 100 : S.ep.closes[i]; }
  function fmtLvl(x) { return S.blind ? x.toFixed(1) : Math.round(x).toLocaleString('en-IN'); }
  function dstr(i) {
    var d = new Date(S.ep.dates[i] + 'T00:00:00Z');
    return d.getUTCDate() + ' ' + ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'][d.getUTCMonth()] + ' ' + d.getUTCFullYear();
  }
  function chart(series, o) {
    // series: [{vals, color, dash, w}], vals length <= n; x spans full episode (the future stays blank)
    var W = 640, H = o.h, pl = 52, pr = 10, pt = 10, pb = 18, n = N();
    var lo = Infinity, hi = -Infinity;
    series.forEach(function (s) { s.vals.forEach(function (v) { if (v < lo) lo = v; if (v > hi) hi = v; }); });
    if (o.base != null) { lo = Math.min(lo, o.base); hi = Math.max(hi, o.base); }
    var span = hi - lo || 1; lo -= span * 0.08; hi += span * 0.08;
    var X = function (i) { return pl + (W - pl - pr) * i / Math.max(1, n - 1); };
    var Y = function (v) { return pt + (H - pt - pb) * (1 - (v - lo) / (hi - lo)); };
    var g = '';
    for (var k = 0; k <= 3; k++) {
      var v = lo + (hi - lo) * k / 3, y = Y(v);
      g += '<line x1="' + pl + '" x2="' + (W - pr) + '" y1="' + y.toFixed(1) + '" y2="' + y.toFixed(1) + '" stroke="#e2e8f0" stroke-width="1"/><text x="' + (pl - 6) + '" y="' + (y + 4).toFixed(1) + '" text-anchor="end" font-size="11" fill="#64748b">' + o.fmt(v) + '</text>';
    }
    if (o.base != null) g += '<line x1="' + pl + '" x2="' + (W - pr) + '" y1="' + Y(o.base).toFixed(1) + '" y2="' + Y(o.base).toFixed(1) + '" stroke="#94a3b8" stroke-dasharray="4 4" stroke-width="1"/>';
    series.forEach(function (s) {
      var d = ''; s.vals.forEach(function (v2, i) { d += (i ? 'L' : 'M') + X(i).toFixed(1) + ' ' + Y(v2).toFixed(1); });
      g += '<path d="' + d + '" fill="none" stroke="' + s.color + '" stroke-width="' + (s.w || 2) + '"' + (s.dash ? ' stroke-dasharray="' + s.dash + '"' : '') + ' stroke-linejoin="round"/>';
    });
    if (o.marks) o.marks.forEach(function (t) {
      var x = X(t.day), y = Y(o.markY(t.day)), up = t.type === 'buy';
      g += up ? '<path d="M' + x.toFixed(1) + ' ' + (y - 3).toFixed(1) + 'l-5 9h10z" fill="#059669" stroke="#fff" stroke-width="1"/>' : '<path d="M' + x.toFixed(1) + ' ' + (y + 3).toFixed(1) + 'l-5 -9h10z" fill="#e11d48" stroke="#fff" stroke-width="1"/>';
    });
    var lab = o.xlab || [];
    lab.forEach(function (t) { g += '<text x="' + X(t.i).toFixed(1) + '" y="' + (H - 4) + '" text-anchor="' + (t.i === 0 ? 'start' : t.i >= n - 1 ? 'end' : 'middle') + '" font-size="11" fill="#64748b">' + t.t + '</text>'; });
    return '<svg viewBox="0 0 ' + W + ' ' + H + '" class="w-full h-auto" role="img" aria-label="' + o.label + '">' + g + '</svg>';
  }

  // ---------------------------------------------------------------- UI
  var REASONS = ['Planned in advance', 'Rebalancing', 'News or headlines', 'Fear of losing more', 'Fear of missing out', 'Just experimenting'];
  function show(id) { ['labSetup', 'labPlay', 'labResult'].forEach(function (x) { $(x).classList.toggle('hidden', x !== id); }); window.scrollTo({ top: 0 }); }

  function renderSetup() {
    var h = '';
    L.episodes.forEach(function (e) {
      h += '<button type="button" data-ep="' + e.id + '" class="epbtn text-left rounded-2xl border border-slate-200 bg-white p-4 hover:border-indigo-400 hover:shadow transition w-full"><p class="text-xs font-bold tracking-wide text-indigo-600">EPISODE ' + e.id.toUpperCase() + '</p>' +
        '<p class="mt-1 font-bold text-slate-900 epname">' + OIQ.esc(e.mystery) + '</p><p class="text-sm text-slate-600 mt-1">' + e.days + ' trading days (about ' + Math.round(e.days / 21) + ' months). Real daily closes.</p></button>';
    });
    h += '<button type="button" data-ep="random" class="epbtn text-left rounded-2xl border border-dashed border-indigo-300 bg-indigo-50 p-4 hover:border-indigo-500 transition w-full"><p class="text-xs font-bold tracking-wide text-indigo-600">SURPRISE ME</p><p class="mt-1 font-bold text-slate-900">Pick one at random</p><p class="text-sm text-slate-600 mt-1">The most honest way to practise.</p></button>';
    $('epList').innerHTML = h;
    Array.prototype.forEach.call(document.querySelectorAll('.epbtn'), function (b) {
      b.addEventListener('click', function () { var id = b.getAttribute('data-ep'); if (id === 'random') id = L.episodes[Math.floor(Math.random() * L.episodes.length)].id; start(id, $('blind').checked); });
    });
  }
  function start(id, blind) {
    var ep = L.episodes.filter(function (e) { return e.id === id; })[0];
    if (!ep) return null;
    stop(); S = newState(ep, blind !== false); R = null;
    OIQ.track('lab_start', { episode: id, blind: S.blind ? 1 : 0 });
    var h = ''; REASONS.forEach(function (r) { h += '<option>' + r + '</option>'; });
    $('reason').innerHTML = h;
    $('sipOn').checked = false; $('sipAmt').value = 25000;
    $('nudge').classList.add('hidden');
    show('labPlay'); renderPlay(); return S;
  }
  function renderPlay() {
    if (!S) return;
    var i = S.i, n = N(), v = value(i), pnl = (v / CASH0 - 1) * 100, dd = (S.peak - v) / S.peak * 100;
    $('stDay').textContent = S.blind ? ('Day ' + (i + 1) + ' of ' + n) : dstr(i);
    $('stLevel').textContent = fmtLvl(lvl(i));
    $('stValue').textContent = OIQ.inr(v);
    $('stCash').textContent = OIQ.inr(S.cash);
    $('stInv').textContent = OIQ.inr(S.units * px(i));
    $('stPnl').textContent = OIQ.pct(pnl);
    $('stPnl').className = 'text-lg font-bold ' + (pnl >= 0 ? 'text-emerald-600' : 'text-rose-600');
    $('stDD').textContent = (dd > 0.05 ? '-' + dd.toFixed(1) + '%' : '0%');
    $('stMk').textContent = mkDD(i) > 0.05 ? '-' + mkDD(i).toFixed(1) + '%' : 'at high';
    var lv = []; for (var k = 0; k <= i; k++) lv.push(lvl(k));
    var xl = S.blind ? [{ i: 0, t: 'Start' }, { i: n - 1, t: 'End unknown' }] : [{ i: 0, t: dstr(0) }, { i: n - 1, t: dstr(n - 1) }];
    $('chartPrice').innerHTML = chart([{ vals: lv, color: '#4f46e5', w: 2 }], { h: 230, fmt: fmtLvl, marks: S.trades, markY: function (d) { return lvl(d); }, xlab: xl, label: 'Market level so far with your buys and sells marked' });
    $('chartVal').innerHTML = chart([{ vals: S.vals.slice(0, i + 1), color: '#7c3aed', w: 2 }], { h: 130, base: CASH0, fmt: function (x) { return (x / 100000).toFixed(1) + 'L'; }, xlab: [], label: 'Your portfolio value so far' });
    var done = i >= n - 1;
    ['bNext', 'bWeek', 'bMonth', 'bPlay'].forEach(function (b) { $(b).disabled = done; $(b).classList.toggle('opacity-40', done); });
    $('bEnd').textContent = done ? 'See my results' : 'Skip to the end and see results';
    var nd = $('nudge');
    if (S.nudge) {
      nd.classList.remove('hidden');
      $('nudgeTxt').textContent = 'Your portfolio is ' + S.nudge.dd.toFixed(0) + '% below its own peak. Notice what you feel right now, then decide what your plan says. Writing it down is part of the practice.';
    } else nd.classList.add('hidden');
    var tl = '';
    S.trades.slice(-6).reverse().forEach(function (t) {
      tl += '<li class="flex justify-between gap-3"><span>' + (S.blind ? 'Day ' + (t.day + 1) : dstr(t.day)) + ' &middot; <strong class="' + (t.type === 'buy' ? 'text-emerald-700' : 'text-rose-700') + '">' + t.type.toUpperCase() + '</strong> ' + (t.auto ? '(auto) ' : '') + '</span><span>' + OIQ.inr(t.amt) + '</span></li>';
    });
    $('tradeLog').innerHTML = tl || '<li class="text-slate-400">No trades yet. Doing nothing is also a choice.</li>';
  }
  function after(fn) { return function () { if (!S || S.finished) return; fn(); renderPlay(); }; }
  function advance(k) {
    if (S) S.nudge = null;
    for (var j = 0; j < k; j++) { if (!step()) break; if (S.nudge) { stop(); break; } }
  }
  function stop() { if (timer) { clearInterval(timer); timer = null; } if ($('bPlay')) $('bPlay').textContent = 'Play'; }
  function play() {
    if (timer) { stop(); return; }
    var sp = +$('speed').value || 1;
    $('bPlay').textContent = 'Pause';
    timer = setInterval(function () { advance(sp); renderPlay(); if (!S || S.i >= N() - 1 || S.nudge) stop(); }, 120);
  }
  function ticketBuy(amt) { var t = buy(amt, $('reason').value, $('note').value.trim()); if (t) { OIQ.track('lab_trade', { type: 'buy' }); $('note').value = ''; } renderPlay(); }
  function ticketSell(f) { var t = sell(f, $('reason').value, $('note').value.trim()); if (t) { OIQ.track('lab_trade', { type: 'sell' }); $('note').value = ''; } renderPlay(); }

  function pctAfter(t) { return (px(N() - 1) / t.price - 1) * 100; }
  function renderResult() {
    var r = R, n = N(), ep = S.ep;
    $('rName').textContent = ep.name;
    $('rWhen').textContent = dstr(0) + ' to ' + dstr(n - 1);
    $('rFacts').textContent = ep.facts;
    $('rStory').textContent = ep.story;
    var rows = [['You', r.final, r.ret, r.maxdd, '#7c3aed'], ['Buy and hold (all in on day 1)', r.bhFinal, r.bhRet, r.bhDD, '#d97706'], ['Auto-invest benchmark (' + r.b.parts + ' equal instalments)', r.sipFinal, r.sipRet, r.sipDD, '#059669'], ['Cash (no return)', CASH0, 0, 0, '#94a3b8']];
    var h = '';
    rows.forEach(function (x) { h += '<tr class="border-t border-slate-100"><td class="py-2 pr-3"><span class="inline-block w-2.5 h-2.5 rounded-full mr-2" style="background:' + x[4] + '"></span>' + x[0] + '</td><td class="py-2 pr-3 font-semibold">' + OIQ.inr(x[1]) + '</td><td class="py-2 pr-3 ' + (x[2] >= 0 ? 'text-emerald-700' : 'text-rose-700') + '">' + OIQ.pct(x[2]) + '</td><td class="py-2">' + (x[3] > 0.05 ? '-' + x[3].toFixed(1) + '%' : '0%') + '</td></tr>'; });
    $('rTable').innerHTML = h;
    $('rChart').innerHTML = chart([{ vals: r.b.cash, color: '#94a3b8', dash: '4 4', w: 1.5 }, { vals: r.b.sip, color: '#059669', w: 2 }, { vals: r.b.bh, color: '#d97706', w: 2 }, { vals: S.vals, color: '#7c3aed', w: 2.5 }],
      { h: 260, base: CASH0, fmt: function (x) { return (x / 100000).toFixed(1) + 'L'; }, xlab: [{ i: 0, t: dstr(0) }, { i: n - 1, t: dstr(n - 1) }], label: 'Your portfolio versus the benchmarks over the whole episode' });
    var o = [];
    o.push('You made <strong>' + r.trades + '</strong> trade' + (r.trades === 1 ? '' : 's') + ' and paid about <strong>' + OIQ.inr(r.cost) + '</strong> in costs (' + (r.cost / CASH0 * 100).toFixed(2) + '% of your starting money, at an illustrative ' + (COST * 100).toFixed(2) + '% per trade).');
    o.push('Your worst fall from a peak was <strong>-' + r.maxdd.toFixed(1) + '%</strong>. The market\'s own worst fall in this episode was <strong>-' + r.mkDD.toFixed(1) + '%</strong>.');
    o.push('On average you were <strong>' + r.avgExpo.toFixed(0) + '%</strong> invested across the episode.');
    if (r.fearSells.length) { var f0 = r.fearSells[0]; o.push('<strong>' + r.fearSells.length + '</strong> of your sales came when the market was at least 10% below its earlier high. From your first such sale the market went on to end <strong>' + OIQ.pct(pctAfter(f0), 0) + '</strong> by the end of the episode.'); }
    if (r.chase.length) o.push('<strong>' + r.chase.length + '</strong> of your purchases came right after the market had already risen 8% or more in the previous month.');
    if (!r.fearSells.length && !r.chase.length && r.trades <= 3) o.push('You traded rarely. In practice that is often the simplest way to avoid costly mistakes, but it also means you had no say in the outcome. Neither is right or wrong.');
    $('rObs').innerHTML = o.map(function (x) { return '<li>' + x + '</li>'; }).join('');
    var tr = '';
    S.trades.filter(function (t) { return !t.auto; }).forEach(function (t) {
      tr += '<tr class="border-t border-slate-100"><td class="py-1.5 pr-3 whitespace-nowrap">' + dstr(t.day) + '</td><td class="py-1.5 pr-3 font-semibold ' + (t.type === 'buy' ? 'text-emerald-700' : 'text-rose-700') + '">' + t.type + '</td><td class="py-1.5 pr-3">' + OIQ.inr(t.amt) + '</td><td class="py-1.5 pr-3">' + OIQ.esc(t.reason) + (t.note ? ': ' + OIQ.esc(t.note) : '') + '</td><td class="py-1.5">' + OIQ.pct(pctAfter(t), 0) + '</td></tr>';
    });
    $('rTrades').innerHTML = tr || '<tr><td class="py-2 text-slate-400" colspan="5">No manual trades.</td></tr>';
    show('labResult');
    saveRun();
  }
  var runId = null;
  function saveRun() {
    var j = OIQ.store.get(JKEY, { runs: [], notes: [] });
    runId = Date.now().toString(36) + Math.floor(Math.random() * 1e4).toString(36);
    var r = R;
    j.runs.unshift({ id: runId, ts: Date.now(), ep: S.ep.id, name: S.ep.name, start: S.ep.dates[0], end: S.ep.dates[N() - 1], blind: S.blind, cash0: CASH0, final: r.final, ret: r.ret, bhRet: r.bhRet, sipRet: r.sipRet, maxdd: r.maxdd, mkDD: r.mkDD,
      cost: r.cost, avgExpo: r.avgExpo, fearSells: r.fearSells.length, chase: r.chase.length,
      trades: S.trades.map(function (t) { return [S.ep.dates[t.day], t.type, Math.round(t.amt), +t.price.toFixed(2), t.reason, t.note, t.auto ? 1 : 0, +pctAfter(t).toFixed(1)]; }),
      checks: S.checks.map(function (c) { return [S.ep.dates[c.day], c.dd, c.feel]; }), reflection: '' });
    j.runs = j.runs.slice(0, 40);
    OIQ.store.set(JKEY, j);
    OIQ.track('lab_finish', { episode: S.ep.id, trades: r.trades, beat_hold: r.ret > r.bhRet ? 1 : 0 });
  }
  function saveReflection() {
    var j = OIQ.store.get(JKEY, { runs: [], notes: [] }), t = $('reflect').value.trim();
    j.runs.forEach(function (x) { if (x.id === runId) x.reflection = t; });
    OIQ.store.set(JKEY, j); $('reflectOk').classList.remove('hidden');
    OIQ.track('journal_save', { kind: 'reflection' });
  }

  // ---------------------------------------------------------------- wire up
  function init() {
    renderSetup();
    var amts = [50000, 100000, 250000];
    var bh = ''; amts.forEach(function (a) { bh += '<button type="button" data-buy="' + a + '" class="tbtn rounded-lg bg-emerald-600 text-white text-sm font-semibold px-3 py-2 hover:bg-emerald-700">Buy ' + OIQ.inr(a) + '</button>'; });
    bh += '<button type="button" data-buy="all" class="tbtn rounded-lg bg-emerald-800 text-white text-sm font-semibold px-3 py-2 hover:bg-emerald-900">Buy with all cash</button>';
    $('buyBtns').innerHTML = bh;
    var sh = ''; [0.25, 0.5, 1].forEach(function (f) { sh += '<button type="button" data-sell="' + f + '" class="tbtn rounded-lg bg-rose-600 text-white text-sm font-semibold px-3 py-2 hover:bg-rose-700">Sell ' + (f === 1 ? 'all' : f * 100 + '%') + '</button>'; });
    $('sellBtns').innerHTML = sh;
    Array.prototype.forEach.call(document.querySelectorAll('[data-buy]'), function (b) { b.addEventListener('click', after(function () { var a = b.getAttribute('data-buy'); ticketBuy(a === 'all' ? S.cash : +a); })); });
    Array.prototype.forEach.call(document.querySelectorAll('[data-sell]'), function (b) { b.addEventListener('click', after(function () { ticketSell(+b.getAttribute('data-sell')); })); });
    $('btnBuyCustom').addEventListener('click', after(function () { ticketBuy(+$('customAmt').value); }));
    $('bNext').addEventListener('click', after(function () { stop(); advance(1); }));
    $('bWeek').addEventListener('click', after(function () { stop(); advance(5); }));
    $('bMonth').addEventListener('click', after(function () { stop(); advance(20); }));
    $('bPlay').addEventListener('click', function () { if (S && !S.finished) { play(); } });
    $('bEnd').addEventListener('click', function () { if (!S) return; finish(); renderResult(); });
    $('sipOn').addEventListener('change', function () { if (S) S.sip.on = this.checked; });
    $('sipAmt').addEventListener('change', function () { if (S) S.sip.amt = Math.max(1000, +this.value || 25000); });
    Array.prototype.forEach.call(document.querySelectorAll('[data-feel]'), function (b) {
      b.addEventListener('click', function () { if (S && S.nudge) { S.checks.push({ day: S.nudge.day, dd: +S.nudge.dd.toFixed(1), feel: b.getAttribute('data-feel') }); S.nudge = null; renderPlay(); } });
    });
    $('nudgeSkip').addEventListener('click', function () { if (S) { S.nudge = null; renderPlay(); } });
    $('saveReflect').addEventListener('click', saveReflection);
    $('again').addEventListener('click', function () { stop(); S = null; R = null; $('reflect').value = ''; $('reflectOk').classList.add('hidden'); show('labSetup'); });
    window.__lab = { start: start, buy: function (a) { return buy(a, 'test', ''); }, sell: function (f) { return sell(f, 'test', ''); }, step: step, advance: advance, finish: function () { finish(); renderResult(); return R; },
      state: function () { return S; }, result: function () { return R; }, setSip: function (on, amt) { S.sip.on = on; S.sip.amt = amt; }, bench: bench };
    window.__labReady = true;
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
