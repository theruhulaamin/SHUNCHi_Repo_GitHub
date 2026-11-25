/* SHUNCHi account (Firebase). Optional: nobody is forced to sign in.
   Loads only when /data/firebase-config.json is filled in. Public API: window.SHAuth */
(function () {
  "use strict";
  var V = "10.14.1", CDN = "https://www.gstatic.com/firebasejs/" + V + "/";
  var d = document, hint = "shunchi_authed";
  function bn() { return d.documentElement.lang === "bn"; }
  function L(en, b) { return bn() ? b : en; }
  function $(s, r) { return (r || d).querySelector(s); }
  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; }); }
  function sha256(t) { return crypto.subtle.digest("SHA-256", new TextEncoder().encode(t)).then(function (b) { return [].map.call(new Uint8Array(b), function (x) { return ("0" + x.toString(16)).slice(-2); }).join(""); }); }

  var api = window.SHAuth = { enabled: false, user: null, profile: null, _cbs: [], _ready: null };
  api.onChange = function (cb) { api._cbs.push(cb); if (api._started) cb(api.user, api.profile); };
  function fire() { api._cbs.forEach(function (cb) { try { cb(api.user, api.profile); } catch (e) {} }); render(); }

  var cfg = null, F = {}, app, auth, db, loading = null;
  function getCfg() {
    if (cfg !== null) return Promise.resolve(cfg);
    return fetch("/data/firebase-config.json", { cache: "no-store" }).then(function (r) { return r.ok ? r.json() : {}; }, function () { return {}; }).then(function (j) { cfg = j && j.apiKey && j.projectId ? j : false; return cfg; });
  }
  function load() {
    if (loading) return loading;
    loading = getCfg().then(function (c) {
      if (!c) throw new Error("not-configured");
      return Promise.all([import(CDN + "firebase-app.js"), import(CDN + "firebase-auth.js"), import(CDN + "firebase-firestore.js")]);
    }).then(function (m) {
      F = {}; [m[0], m[1], m[2]].forEach(function (x) { for (var k in x) F[k] = x[k]; });
      app = F.initializeApp({ apiKey: cfg.apiKey, authDomain: cfg.authDomain || (cfg.projectId + ".firebaseapp.com"), projectId: cfg.projectId, appId: cfg.appId });
      auth = F.getAuth(app); db = F.getFirestore(app); api.enabled = true;
      return new Promise(function (res) {
        var first = true;
        F.onAuthStateChanged(auth, function (u) {
          api.user = u ? { uid: u.uid, email: u.email, name: u.displayName || "", photo: u.photoURL || "", verified: !!u.emailVerified, created: u.metadata && u.metadata.creationTime } : null;
          try { u ? localStorage.setItem(hint, "1") : localStorage.removeItem(hint); } catch (e) {}
          (u ? readProfile() : Promise.resolve(null)).then(function (p) { api.profile = p; api.blocked = !!(p && p.status === "blocked"); api._started = true; if (u && !api._seen) { api._seen = true; F.setDoc(F.doc(db, "users", u.uid), { lastActive: F.serverTimestamp(), email: u.email || "" }, { merge: true }).catch(function () {}); } fire(); if (first) { first = false; res(api); } });
        });
      });
    });
    api._ready = loading; return loading;
  }
  api.ready = function () { return load(); };

  /* ---------- data ---------- */
  function readProfile() {
    var u = auth.currentUser; if (!u) return Promise.resolve(null);
    return F.getDoc(F.doc(db, "users", u.uid)).then(function (s) { var p = s.exists() ? s.data() : {}; if (!p.name) p.name = u.displayName || ""; if (!p.email) p.email = u.email || ""; return p; }, function () { return { name: u.displayName || "", email: u.email || "" }; });
  }
  api.saveProfile = function (p) {
    var u = auth.currentUser; if (!u) return Promise.reject(new Error("signed-out"));
    var rec = { name: String(p.name || "").slice(0, 60), email: u.email || "", phone: String(p.phone || "").slice(0, 30), address: String(p.address || "").slice(0, 160), updatedAt: F.serverTimestamp() };
    return F.setDoc(F.doc(db, "users", u.uid), rec, { merge: true }).then(function () { return u.displayName !== rec.name ? F.updateProfile(u, { displayName: rec.name }) : null; }).then(function () { return readProfile(); }).then(function (pp) { api.profile = pp; api.user.name = rec.name; fire(); return pp; });
  };
  api.addIdea = function (rec) {
    var u = auth.currentUser; if (!u || !rec || !rec.track || api.blocked) return Promise.resolve(false);
    return F.setDoc(F.doc(db, "users", u.uid, "ideas", rec.track), { track: rec.track, title: String(rec.title || "").slice(0, 120), details: String(rec.details || "").slice(0, 1200), type: String(rec.type || "").slice(0, 40), createdAt: F.serverTimestamp() }).then(function () { return true; });
  };
  api.listIdeas = function () {
    var u = auth.currentUser; if (!u) return Promise.resolve([]);
    return F.getDocs(F.collection(db, "users", u.uid, "ideas")).then(function (s) { var a = []; s.forEach(function (x) { a.push(x.data()); }); a.sort(function (x, y) { return ts(y.createdAt) - ts(x.createdAt); }); return a; });
  };
  function ts(v) { return v && v.toMillis ? v.toMillis() : v && v.seconds ? v.seconds * 1000 : +v || 0; }
  api.ts = ts;
  /* per-app saved data for the "More Apps" tools: api.saveAppData("pdf-tool", {...}) */
  api.saveAppData = function (appId, data) { var u = auth.currentUser; if (!u || api.blocked) return Promise.reject(new Error("signed-out")); return F.setDoc(F.doc(db, "users", u.uid, "appdata", String(appId)), { data: data, updatedAt: F.serverTimestamp() }); };
  api.getAppData = function (appId) { var u = auth.currentUser; if (!u) return Promise.resolve(null); return F.getDoc(F.doc(db, "users", u.uid, "appdata", String(appId))).then(function (s) { return s.exists() ? s.data().data : null; }); };
  api.listAppData = function () { var u = auth.currentUser; if (!u) return Promise.resolve([]); return F.getDocs(F.collection(db, "users", u.uid, "appdata")).then(function (s) { var a = []; s.forEach(function (x) { a.push({ id: x.id, data: x.data().data, updatedAt: x.data().updatedAt }); }); return a; }); };
  api.deleteAppData = function (appId) { var u = auth.currentUser; return F.deleteDoc(F.doc(db, "users", u.uid, "appdata", String(appId))); };
  api.listComments = function (slug) {
    return F.getDocs(F.query(F.collection(db, "comments"), F.where("slug", "==", slug))).then(function (s) { var a = []; s.forEach(function (x) { var v = x.data(); v.id = x.id; a.push(v); }); a.sort(function (x, y) { return ts(x.createdAt) - ts(y.createdAt); }); return a; });
  };
  api.myComments = function () { var u = auth.currentUser; if (!u) return Promise.resolve([]); return F.getDocs(F.query(F.collection(db, "comments"), F.where("uid", "==", u.uid))).then(function (s) { var a = []; s.forEach(function (x) { var v = x.data(); v.id = x.id; a.push(v); }); a.sort(function (x, y) { return ts(y.createdAt) - ts(x.createdAt); }); return a; }); };
  api.addComment = function (slug, text) {
    var u = auth.currentUser; if (!u || api.blocked) return Promise.reject(new Error("signed-out")); text = String(text || "").trim().slice(0, 1000); if (!text) return Promise.reject(new Error("empty"));
    return F.addDoc(F.collection(db, "comments"), { slug: slug, uid: u.uid, name: (api.profile && api.profile.name) || u.displayName || "Reader", text: text, createdAt: F.serverTimestamp() });
  };
  api.deleteComment = function (id) { return F.deleteDoc(F.doc(db, "comments", id)); };
  api.exportMine = function () {
    return Promise.all([readProfile(), api.listIdeas(), api.listAppData(), api.myComments()]).then(function (x) { return { account: { email: auth.currentUser.email, uid: auth.currentUser.uid }, profile: x[0], ideas: x[1], appData: x[2], comments: x[3] }; });
  };
  api.deleteAccount = function () {
    var u = auth.currentUser;
    return Promise.all([api.listIdeas(), api.listAppData(), api.myComments()]).then(function (x) {
      var jobs = x[0].map(function (i) { return F.deleteDoc(F.doc(db, "users", u.uid, "ideas", i.track)); }).concat(x[1].map(function (a) { return F.deleteDoc(F.doc(db, "users", u.uid, "appdata", a.id)); }), x[2].map(function (c) { return F.deleteDoc(F.doc(db, "comments", c.id)); }));
      return Promise.all(jobs);
    }).then(function () { return F.deleteDoc(F.doc(db, "users", u.uid)); }).then(function () { return F.deleteUser(u); });
  };

  /* ---------- sign in / up ---------- */
  var ERR = {
    "auth/invalid-credential": ["Wrong email or password.", "ইমেইল বা পাসওয়ার্ড ভুল।"], "auth/wrong-password": ["Wrong email or password.", "ইমেইল বা পাসওয়ার্ড ভুল।"], "auth/user-not-found": ["No account with this email. Create one.", "এই ইমেইলে অ্যাকাউন্ট নেই। নতুন খুলুন।"],
    "auth/email-already-in-use": ["This email already has an account. Log in instead.", "এই ইমেইলে অ্যাকাউন্ট আছে। লগইন করুন।"], "auth/weak-password": ["Password must be at least 6 characters.", "পাসওয়ার্ড কমপক্ষে ৬ অক্ষর হতে হবে।"],
    "auth/invalid-email": ["Enter a valid email.", "সঠিক ইমেইল দিন।"], "auth/popup-closed-by-user": ["Google window was closed.", "Google উইন্ডো বন্ধ করা হয়েছে।"], "auth/cancelled-popup-request": ["Google window was closed.", "Google উইন্ডো বন্ধ করা হয়েছে।"],
    "auth/popup-blocked": ["Your browser blocked the Google window. Allow pop-ups and try again.", "ব্রাউজার Google উইন্ডো আটকেছে। পপ-আপ অনুমতি দিয়ে আবার চেষ্টা করুন।"], "auth/network-request-failed": ["No internet connection.", "ইন্টারনেট সংযোগ নেই।"],
    "auth/too-many-requests": ["Too many tries. Wait a little and try again.", "অনেকবার চেষ্টা হয়েছে। একটু পরে আবার চেষ্টা করুন।"], "auth/unauthorized-domain": ["This website address is not allowed in Firebase yet (Authorized domains).", "এই ওয়েবসাইটের ঠিকানা Firebase-এ অনুমোদিত নয় (Authorized domains)।"],
    "auth/operation-not-allowed": ["This sign-in method is not turned on in Firebase.", "এই সাইন-ইন পদ্ধতি Firebase-এ চালু করা নেই।"], "auth/requires-recent-login": ["For safety, log out, log in again and retry.", "নিরাপত্তার জন্য লগআউট করে আবার লগইন করে চেষ্টা করুন।"]
  };
  function errMsg(e) { var m = ERR[e && e.code]; return m ? L(m[0], m[1]) : L("Something went wrong. Try again.", "কিছু একটা ভুল হয়েছে। আবার চেষ্টা করুন।"); }
  api.signup = function (name, email, pass) {
    return F.createUserWithEmailAndPassword(auth, email, pass).then(function (c) {
      return F.updateProfile(c.user, { displayName: name }).then(function () { return F.setDoc(F.doc(db, "users", c.user.uid), { name: name, email: email, phone: "", address: "", createdAt: F.serverTimestamp() }, { merge: true }); }).then(function () { try { F.sendEmailVerification(c.user); } catch (e) {} });
    });
  };
  api.login = function (email, pass) { return F.signInWithEmailAndPassword(auth, email, pass); };
  api.google = function () {
    var pr = new F.GoogleAuthProvider(); pr.setCustomParameters({ prompt: "select_account" });
    return F.signInWithPopup(auth, pr).then(function (c) {
      var u = c.user; return F.getDoc(F.doc(db, "users", u.uid)).then(function (s) { if (!s.exists()) return F.setDoc(F.doc(db, "users", u.uid), { name: u.displayName || "", email: u.email || "", phone: "", address: "", createdAt: F.serverTimestamp() }); });
    });
  };
  api.reset = function (email) { return F.sendPasswordResetEmail(auth, email); };
  api.verifyEmail = function () { return F.sendEmailVerification(auth.currentUser); };
  api.signOut = function () { return F.signOut(auth); };

  /* ---------- modal ---------- */
  var modal, mode = "login";
  function bi(en, b) { return '<span class="en">' + esc(en) + '</span><span class="bn">' + esc(b) + '</span>'; }
  function buildModal() {
    if (modal) return modal;
    modal = d.createElement("div"); modal.className = "auth-modal"; modal.hidden = true; modal.setAttribute("role", "dialog"); modal.setAttribute("aria-modal", "true");
    modal.innerHTML = '<div class="auth-box"><button type="button" class="auth-x" aria-label="Close">×</button>' +
      '<div class="auth-tabs" role="tablist"><button type="button" data-m="login">' + bi("Log in", "লগইন") + '</button><button type="button" data-m="signup">' + bi("Sign up", "সাইন আপ") + '</button></div>' +
      '<p class="auth-why">' + bi("An account is optional. It saves your ideas, your details and your data in the upcoming tools.", "অ্যাকাউন্ট ঐচ্ছিক। এটি আপনার আইডিয়া, তথ্য ও আসন্ন টুলগুলোর ডেটা সংরক্ষণ করে।") + '</p>' +
      '<button type="button" class="auth-google" id="au-g"><svg viewBox="0 0 48 48" width="18" height="18" aria-hidden="true"><path fill="#EA4335" d="M24 9.5c3.5 0 6.6 1.2 9.1 3.6l6.8-6.8C35.8 2.4 30.3 0 24 0 14.6 0 6.5 5.4 2.6 13.2l7.9 6.1C12.4 13.6 17.7 9.5 24 9.5z"/><path fill="#4285F4" d="M46.5 24.5c0-1.6-.1-3.1-.4-4.5H24v9h12.7c-.6 3-2.3 5.5-4.8 7.2l7.6 5.9c4.5-4.1 7-10.2 7-17.6z"/><path fill="#FBBC05" d="M10.5 28.7c-.5-1.5-.8-3-.8-4.7s.3-3.2.8-4.7l-7.9-6.1C.9 16.4 0 20.1 0 24s.9 7.6 2.6 10.8l7.9-6.1z"/><path fill="#34A853" d="M24 48c6.3 0 11.7-2.1 15.6-5.7l-7.6-5.9c-2.1 1.4-4.8 2.3-8 2.3-6.3 0-11.6-4.1-13.5-9.8l-7.9 6.1C6.5 42.6 14.6 48 24 48z"/></svg><span class="g-login">' + bi("Continue with Google", "Google দিয়ে চালিয়ে যান") + '</span></button>' +
      '<div class="auth-or"><span>' + bi("or", "অথবা") + '</span></div>' +
      '<form id="au-form" novalidate><label class="au-name"><span>' + bi("Name", "নাম") + '</span><input name="name" autocomplete="name" maxlength="60"></label>' +
      '<label><span>' + bi("Email", "ইমেইল") + '</span><input name="email" type="email" autocomplete="email" maxlength="80" required></label>' +
      '<label><span>' + bi("Password", "পাসওয়ার্ড") + '</span><input name="pass" type="password" autocomplete="current-password" minlength="6" maxlength="100" required></label>' +
      '<button type="submit" class="btn btn-primary au-go"><span class="g-login">' + bi("Log in", "লগইন") + '</span><span class="g-signup">' + bi("Create account", "অ্যাকাউন্ট খুলুন") + '</span></button>' +
      '<button type="button" class="au-forgot" id="au-forgot">' + bi("Forgot password?", "পাসওয়ার্ড ভুলে গেছেন?") + '</button><p class="auth-msg" id="au-msg" role="status" aria-live="polite"></p></form></div>';
    d.body.appendChild(modal);
    modal.addEventListener("click", function (e) { if (e.target === modal || e.target.className === "auth-x") close(); });
    d.addEventListener("keydown", function (e) { if (e.key === "Escape" && !modal.hidden) close(); });
    modal.querySelectorAll("[data-m]").forEach(function (b) { b.onclick = function () { setMode(b.dataset.m); }; });
    $("#au-g", modal).onclick = function () { busy(true); api.google().then(function () { close(); }, function (e) { say(errMsg(e)); }).then(function () { busy(false); }); };
    $("#au-forgot", modal).onclick = function () { var em = $("[name=email]", modal).value.trim(); if (!em) { say(L("Type your email above first.", "আগে উপরে ইমেইল লিখুন।")); return; } api.reset(em).then(function () { say(L("Password reset email sent. Check your inbox.", "পাসওয়ার্ড রিসেটের ইমেইল পাঠানো হয়েছে। ইনবক্স দেখুন।"), true); }, function (e) { say(errMsg(e)); }); };
    $("#au-form", modal).addEventListener("submit", function (e) {
      e.preventDefault(); var f = e.target, name = f.name.value.trim(), em = f.email.value.trim(), pw = f.pass.value;
      if (mode === "signup" && !name) { say(L("Please enter your name.", "নাম লিখুন।")); return; }
      if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(em)) { say(L("Enter a valid email.", "সঠিক ইমেইল দিন।")); return; }
      if (pw.length < 6) { say(L("Password must be at least 6 characters.", "পাসওয়ার্ড কমপক্ষে ৬ অক্ষর হতে হবে।")); return; }
      busy(true); say("");
      (mode === "signup" ? api.signup(name, em, pw) : api.login(em, pw)).then(function () { close(); }, function (er) { say(errMsg(er)); }).then(function () { busy(false); });
    });
    return modal;
  }
  function busy(on) { modal.querySelectorAll("button,input").forEach(function (x) { x.disabled = on; }); }
  function say(t, ok) { var m = $("#au-msg", modal); m.textContent = t; m.className = "auth-msg " + (ok ? "ok" : t ? "err" : ""); }
  function setMode(m) {
    mode = m; modal.dataset.mode = m;
    modal.querySelectorAll("[data-m]").forEach(function (b) { b.setAttribute("aria-selected", b.dataset.m === m ? "true" : "false"); });
    $("[name=pass]", modal).autocomplete = m === "signup" ? "new-password" : "current-password"; say("");
  }
  var last;
  function close() { if (modal) modal.hidden = true; d.body.classList.remove("auth-open"); if (last && last.focus) try { last.focus(); } catch (e) {} }
  api.open = function (m) {
    last = d.activeElement;
    return load().then(function () {
      if (api.user) { location.href = profileUrl(); return; }
      buildModal(); setMode(m || "login"); modal.hidden = false; d.body.classList.add("auth-open"); setTimeout(function () { var i = $(m === "signup" ? "[name=name]" : "[name=email]", modal); i && i.focus(); }, 30);
    }, function () { alert(L("Accounts are not turned on yet.", "অ্যাকাউন্ট সুবিধা এখনো চালু হয়নি।")); });
  };
  function profileUrl() { return (d.querySelector(".brand") ? d.querySelector(".brand").getAttribute("href").replace(/index\.html$/, "") : "/") + "account/index.html"; }

  /* ---------- header button ---------- */
  function initials(n) { n = (n || "").trim(); return n ? n.split(/\s+/).slice(0, 2).map(function (w) { return w[0]; }).join("").toUpperCase() : "?"; }
  function render() {
    var b = $("#acct-btn"); if (b) {
      if (api.user) { b.className = "acct-btn in"; b.innerHTML = (api.user.photo ? '<img src="' + esc(api.user.photo) + '" alt="" referrerpolicy="no-referrer">' : '<i>' + esc(initials(api.user.name || api.user.email)) + '</i>') + '<span class="acct-name">' + esc((api.user.name || api.user.email || "").split(" ")[0]) + '</span>'; b.title = L("My profile", "আমার প্রোফাইল"); }
      else { b.className = "acct-btn"; b.innerHTML = bi("Log in", "লগইন"); b.title = ""; }
    }
    var mb = $("#acct-btn-m"); if (mb) mb.innerHTML = api.user ? bi("My profile", "আমার প্রোফাইল") : bi("Log in / Sign up", "লগইন / সাইন আপ");
    d.querySelectorAll("[data-auth-only]").forEach(function (el) { el.hidden = !api.user; });
    d.querySelectorAll("[data-guest-only]").forEach(function (el) { el.hidden = !!api.user; });
    pageHooks();
  }

  /* ---------- idea form autofill ---------- */
  function ideaForm() {
    var f = $("#suggest-form"); if (!f) return;
    var bar = $("#autofill-bar");
    if (!bar) { bar = d.createElement("div"); bar.id = "autofill-bar"; bar.className = "autofill-bar"; f.parentNode.insertBefore(bar, f); }
    if (api.user) {
      bar.innerHTML = '<button type="button" class="btn btn-ghost btn-sm" id="autofill-btn">' + bi("Fill my details from my account", "আমার অ্যাকাউন্ট থেকে তথ্য বসান") + '</button><span class="muted">' + bi("Your idea will also appear in your profile.", "আইডিয়াটি আপনার প্রোফাইলেও দেখা যাবে।") + '</span>';
      $("#autofill-btn").onclick = function () {
        var p = api.profile || {}, u = api.user, set = function (n, v) { var el = f.elements[n]; if (el && v) el.value = v; };
        set("name", p.name || u.name); set("email", p.email || u.email); set("phone", p.phone); set("address", p.address);
        if (!p.phone || !p.address) { var m = $("#suggest-msg"); if (m) { m.className = "suggest-msg err"; m.textContent = L("Add your phone and address in your profile to fill them too.", "ফোন ও ঠিকানাও বসাতে প্রোফাইলে সেগুলো যোগ করুন।"); } }
      };
    } else bar.innerHTML = '<span class="muted">' + bi("Have an account?", "অ্যাকাউন্ট আছে?") + '</span> <button type="button" class="au-link" id="autofill-login">' + bi("Log in to fill your details and track this idea", "লগইন করে তথ্য বসান ও আইডিয়া ট্র্যাক করুন") + '</button>';
    var lg = $("#autofill-login"); if (lg) lg.onclick = function () { api.open("login"); };
  }
  d.addEventListener("shunchi:idea", function (e) { if (api.user && e.detail) api.addIdea(e.detail).catch(function () {}); });

  /* ---------- blog comments ---------- */
  function comments() {
    var box = $("#comments"); if (!box) return; var slug = box.dataset.slug;
    box.hidden = false;
    var list = $("#c-list"), form = $("#c-form"), gate = $("#c-gate");
    gate.hidden = !!api.user; form.hidden = !api.user;
    function draw() {
      api.listComments(slug).then(function (a) {
        $("#c-count").textContent = a.length ? "(" + a.length + ")" : "";
        list.innerHTML = a.length ? a.map(function (c) {
          var mine = api.user && c.uid === api.user.uid, dt = ts(c.createdAt) ? new Date(ts(c.createdAt)).toLocaleDateString(bn() ? "bn-BD" : "en-GB", { day: "numeric", month: "short", year: "numeric" }) : "";
          return '<li class="c-item"><i class="c-av">' + esc(initials(c.name)) + '</i><div><b>' + esc(c.name) + '</b> <time>' + esc(dt) + '</time><p>' + esc(c.text).replace(/\n/g, "<br>") + '</p>' + (mine ? '<button type="button" class="au-link" data-cdel="' + esc(c.id) + '">' + L("Delete", "ডিলিট") + '</button>' : "") + '</div></li>';
        }).join("") : '<li class="c-empty">' + bi("No comments yet. Be the first.", "এখনো কোনো মন্তব্য নেই। প্রথম মন্তব্যটি আপনার হোক।") + '</li>';
        list.querySelectorAll("[data-cdel]").forEach(function (b) { b.onclick = function () { api.deleteComment(b.dataset.cdel).then(draw); }; });
      }, function () { list.innerHTML = '<li class="c-empty">' + bi("Comments could not be loaded.", "মন্তব্য লোড হয়নি।") + '</li>'; });
    }
    draw();
    if (!form._wired) {
      form._wired = true;
      $("#c-login").onclick = function () { api.open("login"); }; $("#c-signup").onclick = function () { api.open("signup"); };
      form.addEventListener("submit", function (e) {
        e.preventDefault(); var ta = form.elements.text, m = $("#c-msg"), t = ta.value.trim(); if (!t) return;
        form.querySelector("button[type=submit]").disabled = true;
        api.addComment(slug, t).then(function () { ta.value = ""; m.textContent = ""; draw(); }, function () { m.textContent = L("Could not post. Try again.", "পোস্ট হয়নি। আবার চেষ্টা করুন।"); }).then(function () { form.querySelector("button[type=submit]").disabled = false; });
      });
    }
  }

  /* ---------- account page ---------- */
  var statusCache;
  function statusFor(code) {
    return (statusCache ? Promise.resolve(statusCache) : fetch("/data/ideas-status.json?t=" + Date.now(), { cache: "no-store" }).then(function (r) { return r.ok ? r.json() : {}; }, function () { return {}; }).then(function (j) { statusCache = j; return j; })).then(function (m) { return sha256(code).then(function (h) { return m[h] || null; }); });
  }
  var SLAB = { pending: ["Pending", "পেন্ডিং"], analysis: ["Under analysis", "বিশ্লেষণ চলছে"], approved: ["Approved", "অনুমোদিত"], rejected: ["Not taken forward", "এগোনো যাচ্ছে না"] };

  var STAGES = [["Received", "গৃহীত"], ["Under review", "পর্যালোচনা"], ["Decision", "সিদ্ধান্ত"]];
  function stepsHtml(rec, bn) {
    var h = rec.h && rec.h.length ? rec.h : [{ s: "pending", t: "", f: "" }, { s: rec.s, t: rec.t, f: rec.f }];
    var stage = function (s) { return s === "pending" ? 0 : s === "analysis" ? 1 : 2; }, by = {};
    h.forEach(function (e) { by[stage(e.s)] = e; });
    if (!by[0]) by[0] = { s: "pending", t: "", f: "" };
    var cur = stage(rec.s), out = '<ol class="steps-tl">';
    for (var i = 0; i < 3; i++) {
      var e = by[i], done = i <= cur && e, cls = done ? "done" + (i === cur ? " now" : "") : "todo", name = STAGES[i][bn ? 1 : 0];
      if (i === 2 && e) { name = e.s === "approved" ? (bn ? "অনুমোদিত" : "Approved") : (bn ? "এগোনো যাচ্ছে না" : "Not taken forward"); cls += e.s === "approved" ? " ok" : " no"; }
      out += '<li class="' + cls + '"><i></i><div><b>' + name + '</b>' + (done && e.t ? ' <time>' + String(e.t).replace(/[<>&"]/g, "") + '</time>' : "") + (done && e.f ? '<p class="step-fb"></p>' : "") + '</div></li>';
    }
    return out + "</ol>";
  }
  function fillStepFeedback(root, rec) {
    var h = rec.h && rec.h.length ? rec.h : [{ s: "pending", f: "" }, { s: rec.s, f: rec.f }], by = {};
    h.forEach(function (e) { by[e.s === "pending" ? 0 : e.s === "analysis" ? 1 : 2] = e; });
    root.querySelectorAll(".steps-tl li").forEach(function (li, i) { var p = li.querySelector(".step-fb"); if (p && by[i]) p.textContent = by[i].f; });
  }
  function download(name, obj) { var a = d.createElement("a"); a.href = URL.createObjectURL(new Blob([JSON.stringify(obj, null, 2)], { type: "application/json" })); a.download = name; d.body.appendChild(a); a.click(); a.remove(); }
  function account() {
    var root = $("#account"); if (!root) return;
    var out = $("#acct-body"), guest = $("#acct-guest");
    guest.hidden = !!api.user; out.hidden = !api.user; if (!api.user) return;
    var u = api.user, p = api.profile || {};
    $("#ac-av").innerHTML = u.photo ? '<img src="' + esc(u.photo) + '" alt="" referrerpolicy="no-referrer">' : esc(initials(p.name || u.name || u.email));
    $("#ac-name").textContent = p.name || u.name || u.email; $("#ac-mail").textContent = u.email + (u.verified ? "" : "");
    $("#ac-since").textContent = u.created ? new Date(u.created).toLocaleDateString(bn() ? "bn-BD" : "en-GB", { day: "numeric", month: "long", year: "numeric" }) : "";
    $("#ac-ver").hidden = u.verified; $("#ac-ver-ok").hidden = !u.verified;
    var f = $("#ac-form"); f.elements.name.value = p.name || u.name || ""; f.elements.phone.value = p.phone || ""; f.elements.address.value = p.address || ""; f.elements.email.value = u.email || "";
    if (!f._wired) {
      f._wired = true;
      f.addEventListener("submit", function (e) { e.preventDefault(); var m = $("#ac-msg"); if (!f.elements.name.value.trim()) { m.className = "auth-msg err"; m.textContent = L("Name is required.", "নাম দিতে হবে।"); return; } api.saveProfile({ name: f.elements.name.value.trim(), phone: f.elements.phone.value.trim(), address: f.elements.address.value.trim() }).then(function () { m.className = "auth-msg ok"; m.textContent = L("Saved.", "সেভ হয়েছে।"); }, function () { m.className = "auth-msg err"; m.textContent = L("Could not save. Try again.", "সেভ হয়নি। আবার চেষ্টা করুন।"); }); });
      $("#ac-out").onclick = function () { api.signOut().then(function () { location.href = "../index.html"; }); };
      $("#ac-ver").onclick = function () { api.verifyEmail().then(function () { this.textContent = L("Verification email sent", "ভেরিফিকেশন ইমেইল পাঠানো হয়েছে"); }.bind(this)); };
      $("#ac-reset").onclick = function () { api.reset(api.user.email).then(function () { var m = $("#ac-pw-msg"); m.className = "auth-msg ok"; m.textContent = L("Password reset email sent.", "পাসওয়ার্ড রিসেটের ইমেইল পাঠানো হয়েছে।"); }); };
      $("#ac-export").onclick = function () { api.exportMine().then(function (x) { download("shunchi-my-data.json", x); }); };
      $("#ac-del").onclick = function () { if (!confirm(L("Delete your account and all saved data? This cannot be undone.", "অ্যাকাউন্ট ও সব সেভ করা ডেটা ডিলিট করবেন? এটি আর ফেরানো যাবে না।"))) return; api.deleteAccount().then(function () { location.href = "../index.html"; }, function (e) { alert(errMsg(e)); }); };
    }
    api.listIdeas().then(function (a) {
      var box = $("#ac-ideas"); $("#ac-ideas-n").textContent = a.length ? "(" + a.length + ")" : "";
      box.innerHTML = a.length ? "" : '<p class="muted">' + bi("No ideas yet. Send one from the More Apps page and it will show here with its status.", "এখনো কোনো আইডিয়া নেই। আরও অ্যাপ পেজ থেকে পাঠান, এখানে স্ট্যাটাসসহ দেখা যাবে।") + '</p>';
      a.forEach(function (x) {
        var el = d.createElement("div"); el.className = "idea-card";
        el.innerHTML = '<div class="ic-top"><b>' + esc(x.title) + '</b><span class="status-pill st-pending">…</span></div><code>' + esc(x.track) + '</code><p class="ic-d">' + esc(x.details) + '</p><p class="ic-fb muted"></p>';
        box.appendChild(el);
        statusFor(x.track).then(function (r) {
          var st = r && SLAB[r.s] ? r.s : "pending", pill = el.querySelector(".status-pill");
          pill.className = "status-pill st-" + st; pill.textContent = L(SLAB[st][0], SLAB[st][1]);
          var fbEl = el.querySelector(".ic-fb");
          if (r) { fbEl.innerHTML = stepsHtml(r, bn()); fillStepFeedback(fbEl, r); } else fbEl.textContent = L("We received it. A status will appear after review.", "আমরা পেয়েছি। পর্যালোচনার পর স্ট্যাটাস দেখা যাবে।");
        });
      });
    }, function () {});
    api.listAppData().then(function (a) {
      var box = $("#ac-data"); box.innerHTML = a.length ? a.map(function (x) { return '<div class="ac-row"><b>' + esc(x.id) + '</b><button type="button" class="au-link" data-ddel="' + esc(x.id) + '">' + L("Delete", "ডিলিট") + '</button></div>'; }).join("") : '<p class="muted">' + bi("Nothing saved yet. Data from the upcoming tools will be kept here.", "এখনো কিছু সেভ নেই। আসন্ন টুলগুলোর ডেটা এখানে থাকবে।") + '</p>';
      box.querySelectorAll("[data-ddel]").forEach(function (b) { b.onclick = function () { api.deleteAppData(b.dataset.ddel).then(account); }; });
    }, function () {});
    api.myComments().then(function (a) {
      var box = $("#ac-comments"); box.innerHTML = a.length ? a.map(function (c) { return '<div class="ac-row"><span>' + esc(c.text.slice(0, 90)) + '</span><a class="au-link" href="../blog/' + esc(c.slug) + '.html#comments">' + L("Open", "খুলুন") + '</a><button type="button" class="au-link" data-xdel="' + esc(c.id) + '">' + L("Delete", "ডিলিট") + '</button></div>'; }).join("") : '<p class="muted">' + bi("You have not commented yet.", "আপনি এখনো মন্তব্য করেননি।") + '</p>';
      box.querySelectorAll("[data-xdel]").forEach(function (b) { b.onclick = function () { api.deleteComment(b.dataset.xdel).then(account); }; });
    }, function () {});
  }
  function blockedNote() {
    var t = L("Your account is blocked, so you cannot comment or save data. Contact support if this is a mistake.", "আপনার অ্যাকাউন্ট ব্লক করা আছে, তাই মন্তব্য বা ডেটা সেভ করা যাবে না। ভুল হলে যোগাযোগ করুন।");
    d.querySelectorAll("#c-form,#acct-body .ac-head").forEach(function (el) { var n = el.parentNode.querySelector(".blocked-note"); if (api.blocked) { if (!n) { n = d.createElement("p"); n.className = "blocked-note"; el.parentNode.insertBefore(n, el); } n.textContent = t; } else if (n) n.remove(); });
    var f = $("#c-form"); if (f && api.blocked) f.hidden = true;
  }
  function pageHooks() { ideaForm(); comments(); account(); blockedNote(); }

  /* ---------- boot ---------- */
  function boot() {
    var b = $("#acct-btn"), mb = $("#acct-btn-m");
    getCfg().then(function (c) {
      if (!c) return;   // accounts are off until the Firebase config is filled in
      d.documentElement.classList.add("auth-on");
      [b, mb].forEach(function (x) { if (x) { x.hidden = false; x.addEventListener("click", function (e) { e.preventDefault(); if (api.user) location.href = profileUrl(); else api.open("login"); }); } });
      var need = false; try { need = !!localStorage.getItem(hint); } catch (e) {}
      if (need || $("[data-needs-auth]")) load().catch(function () {}); else render();
      d.querySelectorAll("[data-open-auth]").forEach(function (x) { x.addEventListener("click", function () { api.open(x.dataset.openAuth); }); });
      d.querySelectorAll(".lang button").forEach(function (x) { x.addEventListener("click", function () { setTimeout(render, 30); }); });
    });
  }
  if (d.readyState === "loading") d.addEventListener("DOMContentLoaded", boot); else boot();
})();
