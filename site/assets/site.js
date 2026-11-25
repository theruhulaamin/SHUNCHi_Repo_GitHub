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
  if (!saved && /^bn/i.test(navigator.language || "")) saved = "bn";
  if (saved === "bn") setLang("bn");

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

/* Idea form: sends the suggestion to the developer's inbox (FormSubmit). Falls back to the mail app if sending fails. */
(function () {
  var form = document.getElementById("suggest-form"); if (!form) return;
  var msg = document.getElementById("suggest-msg"), btn = form.querySelector("button[type=submit]");
  var TO = "voice.shunchi@gmail.com";
  function bn() { return document.documentElement.lang === "bn"; }
  function say(en, b, ok) { msg.textContent = bn() ? b : en; msg.className = "suggest-msg " + (ok ? "ok" : "err"); }
  form.addEventListener("submit", function (e) {
    e.preventDefault();
    var d = new FormData(form);
    if (d.get("_honey")) return;
    var title = (d.get("title") || "").trim(), details = (d.get("details") || "").trim();
    if (!title || !details) { say("Please add the idea name and what it should do.", "আইডিয়ার নাম ও এটি কী কাজ করবে তা লিখুন।", false); return; }
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
        var body = "Type: " + payload.Type + "\nIdea: " + title + "\nDetails: " + details + "\nName: " + payload.Name + "\nContact: " + payload.Contact;
        location.href = "mailto:" + TO + "?subject=" + encodeURIComponent(payload._subject) + "&body=" + encodeURIComponent(body);
        say("Could not send directly. Your mail app opened instead.", "সরাসরি পাঠানো যায়নি। তাই আপনার মেইল অ্যাপ খুলেছে।", false);
      }).then(function () { btn.disabled = false; });
  });
})();
