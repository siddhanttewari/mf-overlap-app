/* OverlapIQ Learn: shared helpers, lesson quizzes, progress. Everything stays in this browser (localStorage). */
(function () {
  'use strict';
  var OIQ = window.OIQ = window.OIQ || {};
  var mem = {};
  OIQ.store = {
    get: function (key, def) {
      try { var s = localStorage.getItem(key); if (s) return JSON.parse(s); } catch (e) {}
      return (key in mem) ? JSON.parse(mem[key]) : def;
    },
    set: function (key, val) {
      var s = JSON.stringify(val); mem[key] = s;
      try { localStorage.setItem(key, s); } catch (e) {}
    }
  };
  OIQ.track = function (n, p) { try { if (typeof window.oiqTrack === 'function') window.oiqTrack(n, p || {}); } catch (e) {} };
  OIQ.inr = function (n) { return '₹' + Math.round(n).toLocaleString('en-IN'); };
  OIQ.pct = function (n, d) { d = d == null ? 1 : d; var r = +n.toFixed(d); if (r === 0) r = 0; return (r > 0 ? '+' : '') + r.toFixed(d) + '%'; };
  OIQ.esc = function (s) { return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]; }); };

  var KEY = 'overlapiq_learn_v1';
  function progress() { var o = OIQ.store.get(KEY, null); return (o && o.done) ? o : { done: {} }; }
  OIQ.progress = progress;
  function markDone(slug, score, total) {
    var o = progress(), prev = o.done[slug];
    o.done[slug] = { score: Math.max(score, prev ? prev.score : 0), total: total, ts: Date.now() };
    OIQ.store.set(KEY, o);
  }

  // ------------------------------------------------------------ quiz on lesson pages
  function initQuiz() {
    var root = document.getElementById('quizRoot'), dataEl = document.getElementById('quizData');
    if (!root || !dataEl) return;
    var Q = JSON.parse(dataEl.textContent), slug = root.getAttribute('data-slug');
    var answered = 0, score = 0;
    function render() {
      answered = 0; score = 0;
      var h = '';
      Q.forEach(function (q, qi) {
        h += '<div class="mb-6" data-q="' + qi + '"><p class="font-semibold text-slate-900 mb-2"><span class="text-indigo-600">' + (qi + 1) + '.</span> ' + OIQ.esc(q.q) + '</p><div class="space-y-2">';
        q.o.forEach(function (o, oi) {
          h += '<button type="button" data-o="' + oi + '" class="qopt w-full text-left rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-sm text-slate-800 hover:border-indigo-300 hover:bg-indigo-50 transition">' + OIQ.esc(o) + '</button>';
        });
        h += '</div><p class="qwhy hidden mt-2 text-sm rounded-lg px-3 py-2"></p></div>';
      });
      h += '<div id="quizDone" class="hidden rounded-xl border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-900"></div>';
      root.innerHTML = h;
      Array.prototype.forEach.call(root.querySelectorAll('.qopt'), function (b) {
        b.addEventListener('click', function () {
          var box = b.closest('[data-q]'), qi = +box.getAttribute('data-q'), oi = +b.getAttribute('data-o');
          if (box.getAttribute('data-done')) return;
          box.setAttribute('data-done', '1');
          var q = Q[qi], ok = oi === q.a;
          answered++; if (ok) score++;
          Array.prototype.forEach.call(box.querySelectorAll('.qopt'), function (x, xi) {
            x.disabled = true; x.classList.remove('hover:border-indigo-300', 'hover:bg-indigo-50');
            if (xi === q.a) { x.classList.add('border-emerald-400', 'bg-emerald-50'); }
            else if (xi === oi) { x.classList.add('border-rose-400', 'bg-rose-50'); }
          });
          var w = box.querySelector('.qwhy'); w.classList.remove('hidden');
          w.classList.add(ok ? 'bg-emerald-50' : 'bg-amber-50', ok ? 'text-emerald-900' : 'text-amber-900');
          w.textContent = (ok ? 'Correct. ' : 'Not quite. ') + q.why;
          OIQ.track('learn_quiz_answer', { lesson: slug, question: qi + 1, correct: ok ? 1 : 0 });
          if (answered === Q.length) {
            markDone(slug, score, Q.length);
            var d = document.getElementById('quizDone'); d.classList.remove('hidden');
            d.innerHTML = '<strong>You got ' + score + ' of ' + Q.length + '.</strong> Lesson marked complete on this device. ' + (score < Q.length ? '<button type="button" id="quizRetry" class="underline font-semibold ml-1">Try again</button>' : 'Nicely done.');
            var r = document.getElementById('quizRetry'); if (r) r.addEventListener('click', render);
            OIQ.track('learn_lesson_complete', { lesson: slug, score: score, total: Q.length });
          }
        });
      });
    }
    render();
  }

  // ------------------------------------------------------------ hub progress
  function initHub() {
    var cards = document.querySelectorAll('[data-lesson]');
    if (!cards.length) return;
    var p = progress(), done = 0, first = null;
    Array.prototype.forEach.call(cards, function (c) {
      var s = c.getAttribute('data-lesson'), d = p.done[s];
      if (d) { done++; var b = c.querySelector('.lbadge'); if (b) { b.classList.remove('hidden'); b.textContent = '✓ ' + d.score + '/' + d.total; } }
      else if (!first) first = s;
    });
    var bar = document.getElementById('progBar'), txt = document.getElementById('progText'), go = document.getElementById('startBtn');
    if (bar) bar.style.width = Math.round(100 * done / cards.length) + '%';
    if (txt) txt.textContent = done + ' of ' + cards.length + ' lessons complete on this device';
    if (go) {
      if (first) { go.setAttribute('href', '/learn/' + first); go.textContent = done ? 'Continue learning →' : 'Start with lesson 1 →'; }
      else { go.setAttribute('href', '/learn/lab'); go.textContent = 'All done. Try the replay lab →'; }
    }
  }

  function boot() { try { initQuiz(); initHub(); } catch (e) { try { OIQ.track('js_error', { where: 'learn', msg: String(e && e.message).slice(0, 80) }); } catch (x) {} } }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot); else boot();
})();
