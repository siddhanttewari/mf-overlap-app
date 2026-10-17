/* OverlapIQ Learn: trade journal. Lab runs plus your own practice notes. Stored only in this browser. */
(function () {
  'use strict';
  var OIQ = window.OIQ, $ = function (id) { return document.getElementById(id); };
  if (!OIQ || !$('jRuns')) return;
  var KEY = 'overlapiq_journal_v1';
  function load() { var j = OIQ.store.get(KEY, null); if (!j || !j.runs) j = { runs: [], notes: [] }; if (!j.notes) j.notes = []; return j; }
  function dfmt(iso) { var d = new Date(iso + 'T00:00:00Z'); return d.getUTCDate() + ' ' + ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'][d.getUTCMonth()] + ' ' + d.getUTCFullYear(); }
  function tsfmt(ts) { var d = new Date(ts); return d.toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' }); }
  var E = OIQ.esc;

  function render() {
    var j = load(), runs = j.runs;
    var sum = '';
    if (runs.length) {
      var tot = runs.length, avgT = runs.reduce(function (a, r) { return a + r.trades.length; }, 0) / tot;
      var beat = runs.filter(function (r) { return r.ret > r.bhRet; }).length;
      var fear = runs.reduce(function (a, r) { return a + (r.fearSells || 0); }, 0);
      var cost = runs.reduce(function (a, r) { return a + (r.cost || 0); }, 0);
      sum = '<div class="grid grid-cols-2 sm:grid-cols-4 gap-3">' +
        [['Replay runs', tot], ['Average trades per run', avgT.toFixed(1)], ['Runs that beat buy-and-hold', beat + ' of ' + tot], ['Sales made in a 10%+ market fall', fear]].map(function (x) {
          return '<div class="rounded-xl border border-slate-200 bg-white p-3"><p class="text-xs text-slate-500">' + x[0] + '</p><p class="text-lg font-bold text-slate-900">' + x[1] + '</p></div>'; }).join('') +
        '</div><p class="text-xs text-slate-500 mt-2">Total costs paid across runs: ' + OIQ.inr(cost) + ' (virtual).</p>';
    }
    $('jSummary').innerHTML = sum;
    var h = '';
    runs.forEach(function (r, ri) {
      h += '<details class="rounded-2xl border border-slate-200 bg-white p-4 mb-3" data-run="' + E(r.id) + '"><summary class="cursor-pointer"><span class="font-bold text-slate-900">' + E(r.name) + '</span> <span class="text-xs text-slate-500">&middot; played ' + tsfmt(r.ts) + '</span>' +
        '<span class="block text-sm text-slate-700 mt-1">You <strong>' + OIQ.pct(r.ret) + '</strong> &middot; buy and hold ' + OIQ.pct(r.bhRet) + ' &middot; auto-invest benchmark ' + OIQ.pct(r.sipRet) + ' &middot; worst fall -' + r.maxdd.toFixed(1) + '%</span></summary>' +
        '<div class="mt-3 text-sm text-slate-700"><p class="text-xs text-slate-500 mb-2">' + dfmt(r.start) + ' to ' + dfmt(r.end) + (r.blind ? ' &middot; played blind' : '') + '</p>';
      if (r.trades.length) {
        h += '<div class="overflow-x-auto"><table class="w-full text-xs" style="min-width:460px"><thead><tr class="text-left text-slate-500"><th class="py-1 pr-3">Date</th><th class="py-1 pr-3">Type</th><th class="py-1 pr-3">Amount</th><th class="py-1 pr-3">Why</th><th class="py-1">Market afterwards</th></tr></thead><tbody>';
        r.trades.forEach(function (t) { h += '<tr class="border-t border-slate-100"><td class="py-1 pr-3 whitespace-nowrap">' + dfmt(t[0]) + '</td><td class="py-1 pr-3">' + t[1] + (t[6] ? ' (auto)' : '') + '</td><td class="py-1 pr-3">' + OIQ.inr(t[2]) + '</td><td class="py-1 pr-3">' + E(t[4]) + (t[5] ? ': ' + E(t[5]) : '') + '</td><td class="py-1">' + OIQ.pct(t[7], 0) + '</td></tr>'; });
        h += '</tbody></table></div>';
      } else h += '<p class="text-xs text-slate-500">No trades. You held cash throughout.</p>';
      if (r.checks && r.checks.length) h += '<p class="mt-2 text-xs"><strong>Check-ins during falls:</strong> ' + r.checks.map(function (c) { return dfmt(c[0]) + ' (portfolio -' + Math.round(c[1]) + '%): ' + E(c[2]); }).join('; ') + '</p>';
      h += '<label class="block mt-3 text-xs font-semibold text-slate-600">What did you learn? What would you do differently?</label><textarea data-ref="' + ri + '" rows="3" maxlength="800" class="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm" placeholder="Write it in your own words">' + E(r.reflection || '') + '</textarea>' +
        '<div class="mt-2 flex gap-3 text-xs"><button type="button" data-save="' + ri + '" class="rounded-lg bg-indigo-600 text-white font-semibold px-3 py-1.5">Save note</button><button type="button" data-del="' + ri + '" class="text-rose-600 underline">Delete this run</button></div></div></details>';
    });
    $('jRuns').innerHTML = h || '<p class="text-sm text-slate-500 rounded-xl border border-dashed border-slate-300 bg-white p-5">No replay runs yet. Finish one in the <a href="/learn/lab" class="text-indigo-600 underline">replay lab</a> and it will appear here, with every trade and the reason you gave.</p>';
    Array.prototype.forEach.call(document.querySelectorAll('[data-save]'), function (b) { b.addEventListener('click', function () {
      var ri = +b.getAttribute('data-save'), jj = load(), ta = document.querySelector('[data-ref="' + ri + '"]'); jj.runs[ri].reflection = ta.value.trim(); OIQ.store.set(KEY, jj); b.textContent = 'Saved'; OIQ.track('journal_save', { kind: 'reflection' }); }); });
    Array.prototype.forEach.call(document.querySelectorAll('[data-del]'), function (b) { b.addEventListener('click', function () {
      if (!confirm('Delete this run from your journal?')) return; var jj = load(); jj.runs.splice(+b.getAttribute('data-del'), 1); OIQ.store.set(KEY, jj); render(); }); });

    var nh = '';
    j.notes.forEach(function (n, ni) {
      nh += '<li class="rounded-xl border border-slate-200 bg-white p-3 text-sm"><div class="flex justify-between gap-3"><span><strong class="' + (n.side === 'Buy' ? 'text-emerald-700' : n.side === 'Sell' ? 'text-rose-700' : 'text-slate-700') + '">' + E(n.side) + '</strong> ' + E(n.what) + (n.qty ? ' &middot; ' + E(n.qty) : '') + ' <span class="text-xs text-slate-500">&middot; ' + E(n.date) + '</span></span><button type="button" data-ndel="' + ni + '" class="text-xs text-rose-600 underline">delete</button></div>' +
        (n.why ? '<p class="text-slate-600 mt-1"><em>Why:</em> ' + E(n.why) + '</p>' : '') + (n.out ? '<p class="text-slate-600 mt-0.5"><em>What happened:</em> ' + E(n.out) + '</p>' : '') + '</li>';
    });
    $('jNotes').innerHTML = nh || '<li class="text-sm text-slate-500">No practice notes yet.</li>';
    Array.prototype.forEach.call(document.querySelectorAll('[data-ndel]'), function (b) { b.addEventListener('click', function () { var jj = load(); jj.notes.splice(+b.getAttribute('data-ndel'), 1); OIQ.store.set(KEY, jj); render(); }); });
  }

  function csvCell(v) { v = String(v == null ? '' : v); return /[",\n]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v; }
  function exportCsv() {
    var j = load(), rows = [['source', 'date', 'side', 'what', 'amount_or_qty', 'price', 'reason', 'note_or_outcome']];
    j.runs.forEach(function (r) { r.trades.forEach(function (t) { rows.push(['replay: ' + r.name, t[0], t[1], 'virtual Nifty 50 fund', t[2], t[3], t[4], t[5]]); }); });
    j.notes.forEach(function (n) { rows.push(['my note', n.date, n.side, n.what, n.qty, '', n.why, n.out]); });
    var blob = new Blob([rows.map(function (r) { return r.map(csvCell).join(','); }).join('\n')], { type: 'text/csv' });
    var a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = 'overlapiq-journal.csv'; document.body.appendChild(a); a.click(); a.remove();
    OIQ.track('journal_export', {});
  }

  function init() {
    render();
    $('nDate').value = new Date().toISOString().slice(0, 10);
    $('nAdd').addEventListener('click', function () {
      var what = $('nWhat').value.trim(); if (!what) { $('nWhat').focus(); return; }
      var j = load(); j.notes.unshift({ date: $('nDate').value, side: $('nSide').value, what: what.slice(0, 80), qty: $('nQty').value.trim().slice(0, 40), why: $('nWhy').value.trim().slice(0, 300), out: $('nOut').value.trim().slice(0, 300) });
      j.notes = j.notes.slice(0, 200); OIQ.store.set(KEY, j);
      ['nWhat', 'nQty', 'nWhy', 'nOut'].forEach(function (x) { $(x).value = ''; });
      OIQ.track('journal_save', { kind: 'note' }); render();
    });
    $('jExport').addEventListener('click', exportCsv);
    $('jClear').addEventListener('click', function () { if (confirm('Delete your whole journal from this browser? This cannot be undone.')) { OIQ.store.set(KEY, { runs: [], notes: [] }); render(); } });
    window.__journalReady = true;
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
