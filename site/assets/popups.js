/* SHUNCHi site pop-ups. Managed from the admin panel (Site pop-ups tab) -> data/site-popups.json.
   Rules per pop-up: running window (start + days), audience, page, delay, how many times a visitor sees it,
   and how often (every visit / once a session / once a day). One shows at a time, at most 4 per visit. */
(function () {
  "use strict";
  var d = document, path = location.pathname;
  if (/\/(gitup|account)(\/|$)/.test(path)) return;
  var KEY = "shunchi_pop2", MAX_PER_VISIT = 4, GAP = 1200;
  function bn() { return d.documentElement.lang === "bn"; }
  function pick(en, b) { return bn() ? (b || en || "") : (en || b || ""); }
  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; }); }
  function ymd(dt) { var m = dt.getMonth() + 1, x = dt.getDate(); return dt.getFullYear() + "-" + (m < 10 ? "0" : "") + m + "-" + (x < 10 ? "0" : "") + x; }
  function load() { try { return JSON.parse(localStorage.getItem(KEY) || "{}") || {}; } catch (e) { return {}; } }
  function save(o) { try { localStorage.setItem(KEY, JSON.stringify(o)); } catch (e) {} }
  function sessGet(id) { try { return sessionStorage.getItem(KEY + id) === "1"; } catch (e) { return false; } }
  function sessSet(id) { try { sessionStorage.setItem(KEY + id, "1"); } catch (e) {} }
  function pageKey() {
    var p = path.replace(/index\.html$/, "").replace(/\/+$/, "");
    if (!p) return "home"; var s = p.split("/").filter(Boolean)[0] || "";
    return /^(blog|apps|download|setup|videos|updates)$/.test(s) ? s : "other";
  }
  function inWindow(p) {
    if (!p.start) return true; var t = ymd(new Date());
    var e = new Date(p.start + "T00:00:00"); e.setDate(e.getDate() + (+p.days || 1) - 1);
    return t >= p.start && t <= ymd(e);
  }
  function eligible(p, st, user) {
    if (!p || p.active === false || !inWindow(p)) return false;
    if (p.pages && p.pages !== "all" && p.pages !== pageKey()) return false;
    if (p.audience === "guests" && user) return false;
    if (p.audience === "members" && !user) return false;
    var r = st[p.id] || { n: 0, last: "" }, times = +p.times || 1;
    if (r.n >= times) return false;
    if (p.every === "session" && sessGet(p.id)) return false;
    if (p.every === "day" && r.last === ymd(new Date())) return false;
    return true;
  }
  var queue = [], shown = 0, openEl = null, lastFocus = null;
  function blocked() { return !!(d.querySelector(".auth-modal:not([hidden])") || d.querySelector(".pc-modal:not([hidden])") || d.querySelector(".auth-open")); }
  function record(p, dismissForever) {
    var st = load(), r = st[p.id] || { n: 0, last: "" };
    r.n = dismissForever ? (+p.times || 1) : r.n + 1; r.last = ymd(new Date()); st[p.id] = r; save(st);
    if (p.every === "session") sessSet(p.id);
  }
  function close() {
    if (!openEl) return; var el = openEl; openEl = null; el.classList.remove("on");
    d.removeEventListener("keydown", onKey, true); d.body.classList.remove("sp-open");
    setTimeout(function () { el.remove(); }, 200);
    if (lastFocus && lastFocus.focus) try { lastFocus.focus(); } catch (e) {}
    setTimeout(next, GAP);
  }
  function onKey(e) {
    if (e.key === "Escape") { e.stopPropagation(); close(); return; }
    if (e.key === "Tab" && openEl) {
      var f = openEl.querySelectorAll("a[href],button"); if (!f.length) return;
      var a = f[0], z = f[f.length - 1];
      if (e.shiftKey && d.activeElement === a) { e.preventDefault(); z.focus(); } else if (!e.shiftKey && d.activeElement === z) { e.preventDefault(); a.focus(); }
    }
  }
  function clean(h) {
    h = String(h || ""); if (!/<[a-z][\s\S]*>/i.test(h)) return esc(h).replace(/\n/g, "<br>");
    var t = d.createElement("template"); t.innerHTML = h; var out = d.createElement("div");
    (function walk(src, dst) {
      [].forEach.call(src.childNodes, function (n) {
        if (n.nodeType === 3) { dst.appendChild(d.createTextNode(n.nodeValue)); return; }
        if (n.nodeType !== 1) return; var tg = n.tagName, el = null;
        if (tg === "B" || tg === "STRONG") el = d.createElement("b");
        else if (tg === "I" || tg === "EM") el = d.createElement("i");
        else if (tg === "U") el = d.createElement("u");
        else if (tg === "BR") { dst.appendChild(d.createElement("br")); return; }
        else if (tg === "UL" || tg === "LI") el = d.createElement(tg.toLowerCase());
        else if (tg === "DIV" || tg === "P") el = d.createElement("div");
        else if (tg === "A") { var hr = n.getAttribute("href") || ""; if (/^https:\/\//i.test(hr)) { el = d.createElement("a"); el.setAttribute("href", hr); el.setAttribute("rel", "noopener noreferrer"); } }
        else if (tg === "SPAN") { var cl = n.className; if (cl === "sp-s1" || cl === "sp-s3" || cl === "sp-s4") { el = d.createElement("span"); el.className = cl; } }
        else if (tg === "SCRIPT" || tg === "STYLE") return;
        if (el) { dst.appendChild(el); walk(n, el); } else walk(n, dst);
      });
    })(t.content, out);
    return out.innerHTML;
  }
  function show(p) {
    shown++; record(p, false); lastFocus = d.activeElement;
    var title = pick(p.title_en, p.title_bn), body = pick(p.body_en, p.body_bn), btn = pick(p.button_en, p.button_bn);
    var url = /^https:\/\/(www\.)?shunchiai\.com(\/|$)/i.test(p.button_url || "") ? p.button_url : "";
    var el = d.createElement("div"); el.className = "sp-ov"; el.setAttribute("role", "dialog"); el.setAttribute("aria-modal", "true"); el.setAttribute("aria-label", title || "SHUNCHi");
    var times = +p.times || 1, left = times - (load()[p.id] || { n: 0 }).n;
    el.innerHTML = '<div class="sp-box" data-style="' + esc(p.style || "info") + '"><button type="button" class="sp-x" aria-label="' + (bn() ? "বন্ধ করুন" : "Close") + '">×</button>' +
      '<div class="sp-ico" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="M6 9a6 6 0 1 1 12 0c0 5 2 6 2 6H4s2-1 2-6zM10 19a2 2 0 0 0 4 0"/></svg></div>' +
      (title ? '<h2>' + esc(title) + '</h2>' : '') + (body ? '<div class="sp-body">' + clean(body) + '</div>' : '') +
      '<div class="sp-act">' + (url && btn ? '<a class="btn btn-primary sp-go" href="' + esc(url) + '">' + esc(btn) + '</a>' : '') + '<button type="button" class="btn btn-ghost sp-skip">' + (bn() ? "বন্ধ করুন" : "Close") + '</button></div>' +
      (times > 1 && left > 0 ? '<button type="button" class="sp-never">' + (bn() ? "আর দেখাবেন না" : "Don't show again") + '</button>' : '') + '</div>';
    d.body.appendChild(el); openEl = el; d.body.classList.add("sp-open");
    requestAnimationFrame(function () { el.classList.add("on"); });
    el.addEventListener("click", function (e) { if (e.target === el || e.target.closest(".sp-x,.sp-skip")) close(); else if (e.target.closest(".sp-never")) { record(p, true); close(); } else if (e.target.closest(".sp-go")) { record(p, true); } });
    d.addEventListener("keydown", onKey, true);
    var f = el.querySelector(".sp-go") || el.querySelector(".sp-skip"); f && f.focus();
  }
  function next() {
    if (openEl || shown >= MAX_PER_VISIT) return;
    if (blocked()) { setTimeout(next, 2000); return; }
    var p = queue.shift(); if (!p) return;
    show(p);
  }
  function start(list, user) {
    var st = load(), q = list.filter(function (p) { return eligible(p, st, user); }).slice(0, MAX_PER_VISIT);
    if (!q.length) return; queue = q;
    var delay = Math.max(0, Math.min(60, +q[0].delay || 0)) * 1000;
    setTimeout(next, Math.max(delay, 600));
  }
  function run() {
    fetch("/data/site-popups.json", { cache: "no-cache" }).then(function (r) { return r.ok ? r.json() : []; }, function () { return []; }).then(function (list) {
      if (!Array.isArray(list) || !list.length) return;
      var needAuth = list.some(function (p) { return p.audience === "guests" || p.audience === "members"; });
      if (!needAuth || !window.SHAuth) return start(list, null);
      var done = false, fin = function () { if (done) return; done = true; start(list, window.SHAuth.user || null); };
      window.SHAuth.ready().then(function () { setTimeout(fin, 700); }, fin); setTimeout(fin, 3500);
    });
  }
  if (d.readyState === "loading") d.addEventListener("DOMContentLoaded", run); else run();
})();
