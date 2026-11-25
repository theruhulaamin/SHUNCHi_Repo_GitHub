/* Shared by every page: EN / বাংলা switch, mobile menu, footer year. */
(function () {
  var root = document.documentElement;
  var enBtns = document.querySelectorAll("[data-lang='en']"), bnBtns = document.querySelectorAll("[data-lang='bn']");
  function setLang(lang) {
    root.lang = lang;
    enBtns.forEach(function (b) { b.setAttribute("aria-pressed", lang === "en"); });
    bnBtns.forEach(function (b) { b.setAttribute("aria-pressed", lang === "bn"); });
    try { localStorage.setItem("shunchi-lang", lang); } catch (e) {}
  }
  enBtns.forEach(function (b) { b.addEventListener("click", function () { setLang("en"); }); });
  bnBtns.forEach(function (b) { b.addEventListener("click", function () { setLang("bn"); }); });
  var saved = null;
  try { saved = localStorage.getItem("shunchi-lang"); } catch (e) {}
  setLang(saved === "en" ? "en" : "bn");

  var btn = document.getElementById("menu-btn"), panel = document.getElementById("menu-panel");
  function closeMenu() { if (!btn) return; document.body.classList.remove("menu-open"); btn.setAttribute("aria-expanded", "false"); }
  if (btn && panel) {
    btn.addEventListener("click", function () {
      var open = document.body.classList.toggle("menu-open");
      btn.setAttribute("aria-expanded", open ? "true" : "false");
    });
    panel.querySelectorAll("a").forEach(function (a) { a.addEventListener("click", closeMenu); });
    document.addEventListener("keydown", function (e) { if (e.key === "Escape") closeMenu(); });
    window.addEventListener("resize", function () { if (window.innerWidth > 900) closeMenu(); });
  }
  var year = document.getElementById("year");
  if (year) year.textContent = new Date().getFullYear();
})();

/* Bottom tab bar: highlight the current page, or the section being read on the home page. */
(function () {
  var tabs = document.querySelectorAll(".tabbar a");
  if (!tabs.length) return;
  var path = location.pathname.replace(/index\.html$/, "");
  function mark(key) { tabs.forEach(function (a) { a.classList.toggle("on", a.getAttribute("data-tab") === key); }); }
  if (/\/apps\/?/.test(path)) return mark("apps");
  if (/\/download\/?/.test(path)) return mark("download");
  if (/\/blog\//.test(path)) return mark("blog");
  var home = /\/(privacy\.html)?$/.test(path) && !/privacy/.test(path);
  if (!home || !("IntersectionObserver" in window)) return mark(home ? "home" : "");
  var map = { setup: "setup", apps: "apps", faq: "faq", developer: "dev" }, current = "home";
  mark("home");
  var io = new IntersectionObserver(function (entries) {
    entries.forEach(function (e) { if (e.isIntersecting) { current = map[e.target.id]; mark(current); } });
    var top = window.scrollY < 300; if (top) mark("home");
  }, { rootMargin: "-45% 0px -50% 0px" });
  Object.keys(map).forEach(function (id) { var el = document.getElementById(id); if (el) io.observe(el); });
  window.addEventListener("scroll", function () { if (window.scrollY < 300) mark("home"); }, { passive: true });
})();

/* Dark / light toggle: remembers the choice; default follows the device. */
(function () {
  var btn = document.getElementById("theme-btn"); if (!btn) return;
  var root = document.documentElement;
  function isDark() {
    var t = root.getAttribute("data-theme");
    return t ? t === "dark" : window.matchMedia && matchMedia("(prefers-color-scheme: dark)").matches;
  }
  function sync() { btn.setAttribute("aria-pressed", isDark() ? "true" : "false"); }
  btn.addEventListener("click", function () {
    var next = isDark() ? "light" : "dark";
    root.setAttribute("data-theme", next);
    try { localStorage.setItem("theme", next); } catch (e) {}
    sync();
  });
  sync();
})();

/* Idea form: sends the suggestion to the developer's inbox (FormSubmit). */
(function () {
  var form = document.getElementById("suggest-form"); if (!form) return;
  var msg = document.getElementById("suggest-msg"), btn = form.querySelector("button[type=submit]");
  var TO = form.getAttribute("data-endpoint") || "";
  function bn() { return document.documentElement.lang === "bn"; }
  function say(en, b, ok) { msg.textContent = bn() ? b : en; msg.className = "suggest-msg " + (ok ? "ok" : "err"); }
  form.addEventListener("submit", function (e) {
    e.preventDefault();
    var d = new FormData(form);
    if (d.get("_honey")) return;
    var title = (d.get("title") || "").trim(), details = (d.get("details") || "").trim();
    if (!title || !details) { say("Please add the idea name and what it should do.", "আইডিয়ার নাম ও এটি কী কাজ করবে তা লিখুন।", false); return; }
    if (!TO) { say("The form is not available right now. Please write to voice.shunchi@gmail.com.", "ফর্ম এখন চালু নেই। অনুগ্রহ করে voice.shunchi@gmail.com-এ লিখুন।", false); return; }
    btn.disabled = true; say("Sending…", "পাঠানো হচ্ছে…", true);
    var payload = {
      _subject: "SHUNCHi idea: " + title, _template: "table", _captcha: "false",
      Type: d.get("type"), Idea: title, Details: details,
      Name: d.get("name") || "-", Contact: d.get("contact") || "-", Language: document.documentElement.lang, Page: location.href
    };
    fetch("https://formsubmit.co/ajax/" + TO, {
      method: "POST", headers: { "Content-Type": "application/json", "Accept": "application/json" }, body: JSON.stringify(payload)
    }).then(function (r) { return r.json().catch(function () { return {}; }).then(function (j) { if (!r.ok || j.success === "false" || j.success === false) throw 0; }); })
      .then(function () { form.reset(); say("Thank you! Your idea reached me.", "ধন্যবাদ! আপনার আইডিয়া আমার কাছে পৌঁছেছে।", true); })
      .catch(function () {
        say("Could not send. Please try again, or write to voice.shunchi@gmail.com.", "পাঠানো যায়নি। আবার চেষ্টা করুন, অথবা voice.shunchi@gmail.com-এ লিখুন।", false);
      }).then(function () { btn.disabled = false; });
  });
})();

/* Site-wide scroll animations. Elements fade up as they enter the screen. No JS or reduced motion = everything just shows. */
(function () {
  var calm = window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (calm || !("IntersectionObserver" in window)) return;
  function run() {
    var sel = [
      "main section .head", ".page-head > *", ".stats > *", ".toolbar",
      ".rules li", ".setup .head", ".steps > li", ".note", ".keys > *", ".pills .pill",
      ".app-row", ".faq details", ".dev > *", ".official", ".idea-box", ".cat-head", ".cat-desc",
      ".dl-card", ".dl-steps li", ".privacy-body > *", "main .alt .wrap > p"
    ].join(",");
    var els = document.querySelectorAll(sel), groups = new Map();
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) { if (e.isIntersecting) { e.target.classList.add("in"); io.unobserve(e.target); } });
    }, { rootMargin: "0px 0px -6% 0px", threshold: 0.06 });
    document.documentElement.classList.add("js-anim");
    els.forEach(function (el) {
      if (el.closest(".tool,.hero,.site-header,.tabbar")) return;
      var p = el.parentElement, i = groups.get(p) || 0; groups.set(p, i + 1);
      el.classList.add("rvx"); el.style.setProperty("--d", Math.min(i, 6) * 70 + "ms");
      io.observe(el);
    });
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", run); else run();
})();

/* Scroll progress bar + header shadow once the page moves. */
(function () {
  var bar = document.createElement("div"); bar.className = "progress"; bar.setAttribute("aria-hidden", "true");
  document.body.appendChild(bar);
  var hdr = document.querySelector(".site-header"), tick = false;
  function upd() {
    tick = false;
    var h = document.documentElement, max = h.scrollHeight - h.clientHeight, y = window.scrollY || h.scrollTop;
    bar.style.transform = "scaleX(" + (max > 0 ? Math.min(1, y / max) : 0) + ")";
    if (hdr) hdr.classList.toggle("scrolled", y > 8);
  }
  window.addEventListener("scroll", function () { if (!tick) { tick = true; requestAnimationFrame(upd); } }, { passive: true });
  upd();
})();

/* Hero demo: the same sentence is "typed" into WhatsApp, Messenger, Email and Notes in turn. */
(function () {
  var demo = document.querySelector("[data-demo]"); if (!demo) return;
  var skin = demo.querySelector(".ds"), typed = demo.querySelector(".typed"), msgs = demo.querySelector(".ds-msgs"), timer = demo.querySelector(".timer"), input = demo.querySelector(".ds-input");
  var name = demo.querySelector(".ds-name"), sub = demo.querySelector(".ds-sub"), av = demo.querySelector(".av"), tabs = [].slice.call(demo.querySelectorAll(".dt")), caret = demo.querySelector(".caret");
  var TXT = { en: "Hi Rahim, the files are ready. I will send them tonight.", bn: "রহিম ভাই, ফাইলগুলো তৈরি। আমি আজ রাতেই পাঠিয়ে দেব।" };
  var APPS = [
    { k: "wa", n: { en: "Rahim", bn: "রহিম" }, s: { en: "online", bn: "অনলাইন" }, p: { en: "Type a message", bn: "মেসেজ লিখুন" }, a: "R", send: 1 },
    { k: "ms", n: { en: "Rahim", bn: "রহিম" }, s: { en: "Active now", bn: "এখন সক্রিয়" }, p: { en: "Aa", bn: "Aa" }, a: "R", send: 1 },
    { k: "em", n: { en: "New message", bn: "নতুন মেইল" }, s: { en: "To: Rahim · Subject: Files", bn: "প্রাপক: রহিম · বিষয়: ফাইল" }, p: { en: "Write your email", bn: "মেইল লিখুন" }, a: "✉" },
    { k: "nt", n: { en: "Notes", bn: "নোটস" }, s: { en: "Today", bn: "আজ" }, p: { en: "Start typing", bn: "লেখা শুরু করুন" }, a: "✎" }
  ];
  function L() { return document.documentElement.lang === "en" ? "en" : "bn"; }
  var calm = window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (calm || !window.Promise) return;
  var seg = window.Intl && Intl.Segmenter ? new Intl.Segmenter(undefined, { granularity: "grapheme" }) : null;
  function pieces(s) { return seg ? [].slice.call(seg.segment(s), function (x) { return x.segment; }) : s.split(/(\s+)/); }
  var run = 0, visible = true, idx = 0;
  function wait(ms, id) { return new Promise(function (r) { setTimeout(function () { r(id === run); }, ms); }); }
  function until(id) { return new Promise(function (r) { (function tick() { if (id !== run) return r(false); if (visible && !document.hidden) return r(true); setTimeout(tick, 400); })(); }); }
  function setApp(i) {
    var a = APPS[i], l = L(); skin.setAttribute("data-skin", a.k); name.textContent = a.n[l]; sub.textContent = a.s[l]; av.textContent = a.a;
    tabs.forEach(function (t) { t.classList.toggle("on", t.getAttribute("data-app") === a.k); });
    msgs.innerHTML = ""; typed.innerHTML = '<span class="ph">' + a.p[l] + "</span>";
  }
  function clock(id) { var s = 0; timer.textContent = "00:00"; var iv = setInterval(function () { if (id !== run) return clearInterval(iv); s++; timer.textContent = "00:0" + Math.min(s, 9); }, 1000); return function () { clearInterval(iv); }; }
  async function cycle(id) {
    while (id === run) {
      if (!(await until(id))) return;
      var a = APPS[idx], l = L();
      skin.classList.add("fade"); if (!(await wait(260, id))) return; setApp(idx); skin.classList.remove("fade");
      demo.classList.add("is-listen"); var stop = clock(id);
      if (!(await wait(1900, id))) { stop(); return; } stop(); demo.classList.remove("is-listen");
      typed.innerHTML = ""; var parts = pieces(TXT[l]), acc = "";
      for (var k = 0; k < parts.length; k++) { acc += parts[k]; typed.textContent = acc; if (!(await wait(/\s/.test(parts[k]) ? 20 : 42, id))) return; }
      if (!(await wait(900, id))) return;
      if (a.send) { var b = document.createElement("div"); b.className = "bub"; b.textContent = TXT[l]; msgs.appendChild(b); typed.innerHTML = '<span class="ph">' + a.p[l] + "</span>"; if (!(await wait(2200, id))) return; }
      else if (!(await wait(2000, id))) return;
      idx = (idx + 1) % APPS.length;
    }
  }
  if ("IntersectionObserver" in window) new IntersectionObserver(function (e) { visible = e[0].isIntersecting; }, { threshold: 0.15 }).observe(demo);
  function start() { run++; cycle(run); }
  start();
  if (window.MutationObserver) new MutationObserver(function () { start(); }).observe(document.documentElement, { attributes: true, attributeFilter: ["lang"] });
})();

/* Setup videos: click the picture to play the YouTube video right there (privacy-friendly embed). */
(function () {
  document.addEventListener("click", function (e) {
    var a = e.target.closest && e.target.closest("a.vid-thumb[data-vid]"); if (!a || e.ctrlKey || e.metaKey || e.shiftKey) return;
    e.preventDefault();
    var f = document.createElement("iframe"); f.src = "https://www.youtube-nocookie.com/embed/" + a.getAttribute("data-vid") + "?autoplay=1&rel=0&modestbranding=1";
    f.allow = "autoplay; encrypted-media; picture-in-picture; fullscreen"; f.allowFullscreen = true; f.title = a.getAttribute("aria-label") || "Video";
    a.replaceWith ? (function () { var box = document.createElement("div"); box.className = "vid-thumb"; box.appendChild(f); a.replaceWith(box); })() : null;
  });
})();
