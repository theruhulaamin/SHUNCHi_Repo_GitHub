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
  var map = { setup: "setup", apps: "apps", faq: "faq" }, current = "home";
  mark("home");
  var io = new IntersectionObserver(function (entries) {
    entries.forEach(function (e) { if (e.isIntersecting) { current = map[e.target.id]; mark(current); } });
    var top = window.scrollY < 300; if (top) mark("home");
  }, { rootMargin: "-45% 0px -50% 0px" });
  Object.keys(map).forEach(function (id) { var el = document.getElementById(id); if (el) io.observe(el); });
  window.addEventListener("scroll", function () { if (window.scrollY < 300) mark("home"); }, { passive: true });
})();
