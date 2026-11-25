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
      try {
        if (F.isSignInWithEmailLink && F.isSignInWithEmailLink(auth, location.href)) {
          var em = ""; try { em = localStorage.getItem("shunchi_email_link") || ""; } catch (e) {}
          if (!em) em = prompt(L("Confirm your email to finish signing in", "সাইন-ইন শেষ করতে আপনার ইমেইল লিখুন")) || "";
          if (em) F.signInWithEmailLink(auth, em, location.href).then(function (c) { try { localStorage.removeItem("shunchi_email_link"); history.replaceState(null, "", location.pathname + location.hash); } catch (e) {} return ensureUserDoc(c.user); }).catch(function () {});
        }
      } catch (e) {}
      return new Promise(function (res) {
        var first = true;
        F.onAuthStateChanged(auth, function (u) {
          api.user = u ? { uid: u.uid, email: u.email, name: u.displayName || "", photo: u.photoURL || "", verified: !!u.emailVerified, providers: (u.providerData || []).map(function (x) { return x.providerId; }), created: u.metadata && u.metadata.creationTime } : null;
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
    "auth/operation-not-allowed": ["This sign-in method is not turned on in Firebase.", "এই সাইন-ইন পদ্ধতি Firebase-এ চালু করা নেই।"], "auth/requires-recent-login": ["For safety, enter your current password or log in again, then retry.", "নিরাপত্তার জন্য বর্তমান পাসওয়ার্ড দিন বা আবার লগইন করে চেষ্টা করুন।"], "auth/credential-already-in-use": ["This sign-in is already linked to another account.", "এই সাইন-ইন অন্য অ্যাকাউন্টে যুক্ত আছে।"], "auth/invalid-action-code": ["This link has expired. Request a new one.", "লিংকের মেয়াদ শেষ। নতুন লিংক নিন।"], "auth/operation-not-allowed": ["This sign-in method is not turned on in Firebase.", "এই সাইন-ইন পদ্ধতি Firebase-এ চালু করা নেই।"]
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
  function ensureUserDoc(u) { return F.getDoc(F.doc(db, "users", u.uid)).then(function (sn) { if (!sn.exists()) return F.setDoc(F.doc(db, "users", u.uid), { name: u.displayName || "", email: u.email || "", phone: "", address: "", createdAt: F.serverTimestamp() }); }); }
  /* Firebase has no numeric email OTP. It has sign-in links (passwordless) and verification links. */
  api.sendLink = function (email) {
    return F.sendSignInLinkToEmail(auth, email, { url: location.origin + "/account/index.html", handleCodeInApp: true }).then(function () { try { localStorage.setItem("shunchi_email_link", email); } catch (e) {} });
  };
  api.hasPassword = function () { return !!(api.user && api.user.providers.indexOf("password") >= 0); };
  api.hasGoogle = function () { return !!(api.user && api.user.providers.indexOf("google.com") >= 0); };
  /* set (Google users) or change (password users) the password. current = required for password users when Firebase asks for a fresh login. */
  api.setPassword = function (pw, current) {
    var u = auth.currentUser;
    function again() {
      if (api.hasPassword() && current) return F.reauthenticateWithCredential(u, F.EmailAuthProvider.credential(u.email, current));
      if (api.hasGoogle()) { var pr = new F.GoogleAuthProvider(); return F.reauthenticateWithPopup(u, pr); }
      var e = new Error("x"); e.code = "auth/requires-recent-login"; throw e;
    }
    return F.updatePassword(u, pw).catch(function (e) {
      if (e && e.code === "auth/requires-recent-login") return Promise.resolve().then(again).then(function () { return F.updatePassword(u, pw); });
      throw e;
    }).then(function () { return u.reload(); }).then(function () { api.user.providers = (auth.currentUser.providerData || []).map(function (x) { return x.providerId; }); fire(); });
  };
  api.refreshUser = function () {
    var u = auth.currentUser; if (!u) return Promise.resolve();
    return u.reload().then(function () { return u.getIdToken(true); }).then(function () { var c = auth.currentUser; api.user.verified = !!c.emailVerified; api.user.providers = (c.providerData || []).map(function (x) { return x.providerId; }); fire(); });
  };
  api.reset = function (email) { return F.sendPasswordResetEmail(auth, email); };
  api.verifyEmail = function () { return F.sendEmailVerification(auth.currentUser); };
  api.signOut = function () { return F.signOut(auth); };

  /* ---------- modal ---------- */
  var modal, mode = "login";
  function bi(en, b) { return '<span class="en">' + esc(en) + '</span><span class="bn">' + esc(b) + '</span>'; }
  var GSVG = '<svg viewBox="0 0 48 48" width="18" height="18" aria-hidden="true"><path fill="#EA4335" d="M24 9.5c3.5 0 6.6 1.2 9.1 3.6l6.8-6.8C35.8 2.4 30.3 0 24 0 14.6 0 6.5 5.4 2.6 13.2l7.9 6.1C12.4 13.6 17.7 9.5 24 9.5z"/><path fill="#4285F4" d="M46.5 24.5c0-1.6-.1-3.1-.4-4.5H24v9h12.7c-.6 3-2.3 5.5-4.8 7.2l7.6 5.9c4.5-4.1 7-10.2 7-17.6z"/><path fill="#FBBC05" d="M10.5 28.7c-.5-1.5-.8-3-.8-4.7s.3-3.2.8-4.7l-7.9-6.1C.9 16.4 0 20.1 0 24s.9 7.6 2.6 10.8l7.9-6.1z"/><path fill="#34A853" d="M24 48c6.3 0 11.7-2.1 15.6-5.7l-7.6-5.9c-2.1 1.4-4.8 2.3-8 2.3-6.3 0-11.6-4.1-13.5-9.8l-7.9 6.1C6.5 42.6 14.6 48 24 48z"/></svg>';
  function buildModal() {
    if (modal) return modal;
    modal = d.createElement("div"); modal.className = "auth-modal"; modal.hidden = true; modal.setAttribute("role", "dialog"); modal.setAttribute("aria-modal", "true");
    modal.innerHTML = '<div class="auth-box"><button type="button" class="auth-x" aria-label="Close">×</button>' +
      '<div class="auth-head"><img src="' + (d.querySelector(".brand img") ? d.querySelector(".brand img").getAttribute("src") : "/assets/shunchi-logo.png") + '" alt="SHUNCHi" height="30"><h2 class="t-login">' + bi("Welcome back", "স্বাগতম") + '</h2><h2 class="t-signup">' + bi("Create your account", "অ্যাকাউন্ট খুলুন") + '</h2>' +
      '<p>' + bi("Free and optional. Save your ideas, track their progress and comment on posts.", "ফ্রি ও ঐচ্ছিক। আইডিয়া সেভ করুন, অগ্রগতি দেখুন ও মন্তব্য করুন।") + '</p></div>' +
      '<button type="button" class="auth-google" id="au-g">' + GSVG + '<span>' + bi("Continue with Google", "Google দিয়ে চালিয়ে যান") + '</span></button>' +
      '<div class="auth-or"><span>' + bi("or use email", "অথবা ইমেইল দিয়ে") + '</span></div>' +
      '<form id="au-form" novalidate><label class="au-name"><span>' + bi("Full name", "পুরো নাম") + '</span><input name="name" autocomplete="name" maxlength="60" placeholder="' + L("Your name", "আপনার নাম") + '"></label>' +
      '<label><span>' + bi("Email", "ইমেইল") + '</span><input name="email" type="email" autocomplete="email" maxlength="80" placeholder="you@example.com" required></label>' +
      '<label class="au-pass"><span>' + bi("Password", "পাসওয়ার্ড") + '</span><div class="pw-wrap"><input name="pass" type="password" autocomplete="current-password" minlength="6" maxlength="100" placeholder="••••••••" required><button type="button" class="pw-eye" aria-label="Show password">' + '<svg viewBox="0 0 24 24"><path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/></svg></button></div></label>' +
      '<button type="submit" class="btn btn-primary au-go"><span class="t-login">' + bi("Log in", "লগইন") + '</span><span class="t-signup">' + bi("Create account", "অ্যাকাউন্ট খুলুন") + '</span></button>' +
      '<div class="au-links"><button type="button" class="au-forgot" id="au-forgot">' + bi("Forgot password?", "পাসওয়ার্ড ভুলে গেছেন?") + '</button><button type="button" class="au-forgot" id="au-link">' + bi("Email me a sign-in link", "ইমেইলে সাইন-ইন লিংক নিন") + '</button></div>' +
      '<p class="auth-msg" id="au-msg" role="status" aria-live="polite"></p></form>' +
      '<p class="auth-switch"><span class="t-login">' + bi("New here?", "নতুন?") + ' <button type="button" class="au-link" data-m="signup">' + bi("Create an account", "অ্যাকাউন্ট খুলুন") + '</button></span><span class="t-signup">' + bi("Already have an account?", "অ্যাকাউন্ট আছে?") + ' <button type="button" class="au-link" data-m="login">' + bi("Log in", "লগইন") + '</button></span></p></div>';
    d.body.appendChild(modal);
    modal.addEventListener("click", function (e) { if (e.target === modal || e.target.className === "auth-x") close(); });
    d.addEventListener("keydown", function (e) { if (e.key === "Escape" && !modal.hidden) close(); });
    modal.querySelectorAll("[data-m]").forEach(function (b) { b.onclick = function () { setMode(b.dataset.m); }; });
    $(".pw-eye", modal).onclick = function () { var i = $("[name=pass]", modal); i.type = i.type === "password" ? "text" : "password"; };
    $("#au-g", modal).onclick = function () { busy(true); api.google().then(function () { close(); }, function (e) { say(errMsg(e)); }).then(function () { busy(false); }); };
    $("#au-forgot", modal).onclick = function () { var em = $("[name=email]", modal).value.trim(); if (!em) { say(L("Type your email above first.", "আগে উপরে ইমেইল লিখুন।")); return; } api.reset(em).then(function () { say(L("Password reset email sent. Check your inbox.", "পাসওয়ার্ড রিসেটের ইমেইল পাঠানো হয়েছে। ইনবক্স দেখুন।"), true); }, function (e) { say(errMsg(e)); }); };
    $("#au-link", modal).onclick = function () { var em = $("[name=email]", modal).value.trim(); if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(em)) { say(L("Type your email above first.", "আগে উপরে ইমেইল লিখুন।")); return; } api.sendLink(em).then(function () { say(L("Sign-in link sent. Open it from your email on this device.", "সাইন-ইন লিংক পাঠানো হয়েছে। এই ডিভাইসে ইমেইল থেকে খুলুন।"), true); }, function (e) { say(errMsg(e)); }); };
    $("#au-form", modal).addEventListener("submit", function (e) {
      e.preventDefault(); var f = e.target, name = f.name.value.trim(), em = f.email.value.trim(), pw = f.pass.value;
      if (mode === "signup" && !name) { say(L("Please enter your name.", "নাম লিখুন।")); return; }
      if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(em)) { say(L("Enter a valid email.", "সঠিক ইমেইল দিন।")); return; }
      if (pw.length < 6) { say(L("Password must be at least 6 characters.", "পাসওয়ার্ড কমপক্ষে ৬ অক্ষর হতে হবে।")); return; }
      busy(true); say("");
      (mode === "signup" ? api.signup(name, em, pw) : api.login(em, pw)).then(function () { close(); if (mode === "signup") d.dispatchEvent(new CustomEvent("shunchi:signup")); }, function (er) { say(errMsg(er)); }).then(function () { busy(false); });
    });
    return modal;
  }
  function busy(on) { modal.querySelectorAll("button,input").forEach(function (x) { x.disabled = on; }); }
  function say(t, ok) { var m = $("#au-msg", modal); m.textContent = t; m.className = "auth-msg " + (ok ? "ok" : t ? "err" : ""); }
  function setMode(m) {
    mode = m; modal.dataset.mode = m;
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

  /* ---------- header button + menu ---------- */
  function initials(n) { n = (n || "").trim(); return n ? n.split(/\s+/).slice(0, 2).map(function (w) { return w[0]; }).join("").toUpperCase() : "?"; }
  function avatar(cls) { return api.user.photo ? '<img class="' + cls + '" src="' + esc(api.user.photo) + '" alt="" referrerpolicy="no-referrer">' : '<i class="' + cls + '">' + esc(initials(api.user.name || api.user.email)) + '</i>'; }
  function acctUrl(h) { return profileUrl() + (h ? "#" + h : ""); }
  var menu;
  function closeMenu() { if (menu) menu.hidden = true; var b = $("#acct-btn"); if (b) b.setAttribute("aria-expanded", "false"); }
  function toggleMenu() {
    var b = $("#acct-btn"); if (!api.user || !b) return;
    if (!menu) { menu = d.createElement("div"); menu.className = "acct-menu"; menu.hidden = true; d.body.appendChild(menu); d.addEventListener("click", function (e) { if (menu && !menu.hidden && !menu.contains(e.target) && !b.contains(e.target)) closeMenu(); }); d.addEventListener("keydown", function (e) { if (e.key === "Escape") closeMenu(); }); }
    if (!menu.hidden) { closeMenu(); return; }
    menu.innerHTML = '<div class="am-head">' + avatar("am-av") + '<div><b>' + esc(api.user.name || api.user.email) + '</b><span>' + esc(api.user.email) + '</span></div></div>' +
      '<a href="' + acctUrl("profile") + '"><svg viewBox="0 0 24 24"><circle cx="12" cy="8" r="3.5"/><path d="M5 20c0-3.6 3-6 7-6s7 2.4 7 6"/></svg>' + bi("My profile", "আমার প্রোফাইল") + '</a>' +
      '<a href="' + acctUrl("ideas") + '"><svg viewBox="0 0 24 24"><path d="M9 18h6M10 21h4M12 3a6 6 0 0 0-3.5 10.9c.6.5 1 1.2 1 2.1h5c0-.9.4-1.6 1-2.1A6 6 0 0 0 12 3z"/></svg>' + bi("My ideas", "আমার আইডিয়া") + '</a>' +
      '<a href="' + acctUrl("security") + '"><svg viewBox="0 0 24 24"><rect x="5" y="11" width="14" height="9" rx="2"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/></svg>' + bi("Security", "নিরাপত্তা") + '</a>' +
      '<button type="button" id="am-out"><svg viewBox="0 0 24 24"><path d="M15 4h3a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-3M10 8l-4 4 4 4M6 12h10"/></svg>' + bi("Log out", "লগআউট") + '</button>';
    var r = b.getBoundingClientRect(); menu.style.top = (r.bottom + 8 + window.scrollY) + "px"; menu.style.right = Math.max(12, d.documentElement.clientWidth - r.right) + "px";
    menu.hidden = false; b.setAttribute("aria-expanded", "true");
    $("#am-out", menu).onclick = function () { closeMenu(); api.signOut(); };
  }
  function render() {
    var b = $("#acct-btn"); if (b) {
      if (api.user) { b.className = "acct-btn in"; b.innerHTML = avatar("ab-av") + '<span class="acct-name">' + esc((api.user.name || api.user.email || "").split(" ")[0]) + '</span><svg class="ab-car" viewBox="0 0 24 24"><path d="M6 9l6 6 6-6"/></svg>'; b.setAttribute("aria-haspopup", "menu"); b.title = ""; }
      else { b.className = "acct-btn"; b.innerHTML = '<svg viewBox="0 0 24 24" class="ab-ic"><circle cx="12" cy="8" r="3.5"/><path d="M5 20c0-3.6 3-6 7-6s7 2.4 7 6"/></svg>' + bi("Log in", "লগইন"); b.removeAttribute("aria-haspopup"); closeMenu(); }
    }
    var mb = $("#acct-btn-m"); if (mb) mb.innerHTML = api.user ? bi("My profile", "আমার প্রোফাইল") : bi("Log in / Sign up", "লগইন / সাইন আপ");
    var tb = $('.tabbar a[data-tab="profile"]'); if (tb) { var sv = tb.querySelector("svg,.tb-av"); if (api.user) { if (sv && sv.tagName.toLowerCase() === "svg") { tb._svg = sv; var i = d.createElement("i"); i.className = "tb-av"; i.textContent = initials(api.user.name || api.user.email); sv.replaceWith(i); } else if (sv) sv.textContent = initials(api.user.name || api.user.email); } else if (tb._svg && sv) { sv.replaceWith(tb._svg); } }
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
    var canPost = !!api.user && api.user.verified && !api.blocked, ver = $("#c-verify");
    gate.hidden = !!api.user; form.hidden = !canPost; if (ver) ver.hidden = !(api.user && !api.user.verified);
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
  var acctWired = false, paneNow = "profile", PANES = ["profile", "ideas", "data", "comments", "security"];
  function showPane(k) {
    if (PANES.indexOf(k) < 0) k = "profile"; paneNow = k;
    d.querySelectorAll(".ac-pane").forEach(function (el) { el.hidden = el.dataset.pane !== k; });
    d.querySelectorAll(".ac-nav button").forEach(function (el) { el.setAttribute("aria-selected", el.dataset.pane === k ? "true" : "false"); });
    try { history.replaceState(null, "", "#" + k); } catch (e) {}
  }
  function fmtDate(v) { var t = ts(v); return t ? new Date(t).toLocaleDateString(bn() ? "bn-BD" : "en-GB", { day: "numeric", month: "short", year: "numeric" }) : ""; }
  function renderIdeas(a) {
    var box = $("#ac-ideas"); $("#ac-ideas-n").textContent = a.length ? "(" + a.length + ")" : ""; $("#st-ideas").textContent = a.length;
    if (!a.length) { box.innerHTML = '<div class="empty-state"><svg viewBox="0 0 24 24"><path d="M9 18h6M10 21h4M12 3a6 6 0 0 0-3.5 10.9c.6.5 1 1.2 1 2.1h5c0-.9.4-1.6 1-2.1A6 6 0 0 0 12 3z"/></svg><b>' + L("No ideas yet", "এখনো কোনো আইডিয়া নেই") + '</b><span>' + L("Have an app or tool in mind? Share it and follow its progress here.", "কোনো অ্যাপ বা টুলের আইডিয়া আছে? জানান, অগ্রগতি এখানেই দেখুন।") + '</span><button type="button" class="btn btn-primary btn-sm" data-newidea>' + L("Share your first idea", "প্রথম আইডিয়া জানান") + '</button></div>'; var nb = box.querySelector("[data-newidea]"); if (nb) nb.onclick = openIdeaForm; return; }
    box.innerHTML = "";
    a.forEach(function (x) {
      var el = d.createElement("article"); el.className = "idea-card";
      el.innerHTML = '<div class="ic-top"><h3>' + esc(x.title) + '</h3><span class="status-pill st-pending">…</span></div>' +
        '<div class="ic-meta">' + (x.type ? '<span class="chip-v">' + esc(x.type) + '</span>' : "") + '<button type="button" class="ic-code" title="' + L("Copy tracking number", "ট্র্যাকিং নম্বর কপি করুন") + '">' + esc(x.track) + '<svg viewBox="0 0 24 24"><rect x="9" y="9" width="11" height="11" rx="2"/><path d="M5 15V6a2 2 0 0 1 2-2h9"/></svg></button><time>' + esc(fmtDate(x.createdAt)) + '</time></div>' +
        '<p class="ic-d">' + esc(x.details) + '</p><div class="ic-steps"></div>';
      box.appendChild(el);
      el.querySelector(".ic-code").onclick = function () { try { navigator.clipboard.writeText(x.track); this.classList.add("copied"); } catch (e) {} };
      var stepsBox = el.querySelector(".ic-steps"), first = { s: "pending", t: new Date(ts(x.createdAt) || Date.now()).toISOString().slice(0, 10), f: "" };
      stepsBox.innerHTML = stepsHtml({ s: "pending", t: first.t, f: "", h: [first] }, bn());
      statusFor(x.track).then(function (r) {
        var st = r && SLAB[r.s] ? r.s : "pending", pill = el.querySelector(".status-pill");
        pill.className = "status-pill st-" + st; pill.textContent = L(SLAB[st][0], SLAB[st][1]);
        if (r) { if (!r.h || !r.h.length) r.h = [first, { s: r.s, t: r.t, f: r.f }]; stepsBox.innerHTML = stepsHtml(r, bn()); fillStepFeedback(stepsBox, r); }
      });
    });
  }
  function loadLists() {
    api.listIdeas().then(renderIdeas, function () {});
    api.listAppData().then(function (a) {
      $("#st-data").textContent = a.length; var box = $("#ac-data");
      box.innerHTML = a.length ? a.map(function (x) { return '<div class="ac-row"><div><b>' + esc(x.id) + '</b><span class="muted">' + esc(fmtDate(x.updatedAt)) + '</span></div><button type="button" class="au-link" data-ddel="' + esc(x.id) + '">' + L("Delete", "ডিলিট") + '</button></div>'; }).join("") : '<div class="empty-state small"><b>' + L("Nothing saved yet", "এখনো কিছু সেভ নেই") + '</b><span>' + L("Data from the upcoming tools will be kept here.", "আসন্ন টুলগুলোর ডেটা এখানে থাকবে।") + '</span></div>';
      box.querySelectorAll("[data-ddel]").forEach(function (b) { b.onclick = function () { api.deleteAppData(b.dataset.ddel).then(loadLists); }; });
    }, function () {});
    api.myComments().then(function (a) {
      $("#st-comments").textContent = a.length; var box = $("#ac-comments");
      box.innerHTML = a.length ? a.map(function (c) { return '<div class="ac-row"><div><span>' + esc(c.text.slice(0, 120)) + '</span><span class="muted">' + esc(c.slug) + ' · ' + esc(fmtDate(c.createdAt)) + '</span></div><span class="ac-act"><a class="au-link" href="../blog/' + esc(c.slug) + '.html#comments">' + L("Open", "খুলুন") + '</a><button type="button" class="au-link" data-xdel="' + esc(c.id) + '">' + L("Delete", "ডিলিট") + '</button></span></div>'; }).join("") : '<div class="empty-state small"><b>' + L("No comments yet", "এখনো কোনো মন্তব্য নেই") + '</b><span>' + L("Your comments on blog posts show up here.", "ব্লগে আপনার মন্তব্য এখানে দেখা যাবে।") + '</span></div>';
      box.querySelectorAll("[data-xdel]").forEach(function (b) { b.onclick = function () { api.deleteComment(b.dataset.xdel).then(loadLists); }; });
    }, function () {});
  }
  function openIdeaForm() {
    showPane("ideas"); var f = $("#ai-form"); f.hidden = false;
    var p = api.profile || {}, need = !(p.name && api.user.email && p.phone && p.address); $("#ai-need").hidden = !need; f.querySelector("[type=submit]").disabled = need;
    var t = f.elements.title; if (t) t.focus();
  }
  function methodsHtml() {
    var u = api.user, row = function (name, ok, txt, extra) { return '<div class="method"><div><b>' + name + '</b><span class="muted">' + txt + '</span></div><span class="chip-v' + (ok ? " ok" : "") + '">' + (ok ? L("Connected", "যুক্ত") : L("Not set", "নেই")) + '</span>' + (extra || "") + '</div>'; };
    return row(L("Email and password", "ইমেইল ও পাসওয়ার্ড"), api.hasPassword(), esc(u.email), api.hasPassword() ? "" : '<button type="button" class="au-link" data-goto-pw>' + L("Set password", "পাসওয়ার্ড দিন") + '</button>') +
      row("Google", api.hasGoogle(), api.hasGoogle() ? L("Sign in with one click", "এক ক্লিকে সাইন-ইন") : L("Use “Continue with Google” on the login screen.", "লগইন স্ক্রিনে “Google দিয়ে চালিয়ে যান” ব্যবহার করুন।")) +
      '<div class="method"><div><b>' + L("Email verification", "ইমেইল ভেরিফিকেশন") + '</b><span class="muted">' + L("Needed to post comments.", "মন্তব্য করতে লাগবে।") + '</span></div><span class="chip-v' + (u.verified ? " ok" : "") + '">' + (u.verified ? L("Verified", "ভেরিফাইড") : L("Not verified", "ভেরিফাই হয়নি")) + '</span></div>';
  }
  function fillSecurity() {
    $("#ac-methods").innerHTML = methodsHtml();
    var g = $("[data-goto-pw]"); if (g) g.onclick = function () { var i = $("#pw-form [name=pw]"); i.scrollIntoView({ behavior: "smooth", block: "center" }); i.focus(); };
    var has = api.hasPassword();
    $("#pw-title").textContent = has ? L("Change password", "পাসওয়ার্ড বদলান") : L("Set a password", "পাসওয়ার্ড সেট করুন");
    $("#pw-help").textContent = has ? L("Use at least 6 characters.", "কমপক্ষে ৬ অক্ষর দিন।") : L("You signed in with Google. Add a password to also log in with your email.", "আপনি Google দিয়ে সাইন-ইন করেছেন। পাসওয়ার্ড দিলে ইমেইল দিয়েও লগইন করতে পারবেন।");
    $("#pw-go").textContent = has ? L("Change password", "পাসওয়ার্ড বদলান") : L("Set password", "পাসওয়ার্ড সেট করুন");
    $("#pw-cur-wrap").hidden = !has;
  }
  function account() {
    var root = $("#account"); if (!root) return;
    var out = $("#acct-body"), guest = $("#acct-guest");
    guest.hidden = !!api.user; out.hidden = !api.user; if (!api.user) return;
    var u = api.user, p = api.profile || {}, nm = p.name || u.name || (u.email || "").split("@")[0];
    $("#ac-av").innerHTML = u.photo ? '<img src="' + esc(u.photo) + '" alt="" referrerpolicy="no-referrer">' : esc(initials(nm));
    $("#ac-name").textContent = nm; $("#ac-mail").textContent = u.email; $("#ac-mail").hidden = !u.email || nm === u.email;
    $("#ac-since").textContent = u.created ? new Date(u.created).toLocaleDateString(bn() ? "bn-BD" : "en-GB", { month: "short", year: "numeric" }) : "-";
    $("#ac-verify").hidden = u.verified; $("#ac-ver-ok").hidden = !u.verified;
    $("#ac-prov").textContent = (api.hasGoogle() ? "Google" : "") + (api.hasGoogle() && api.hasPassword() ? " + " : "") + (api.hasPassword() ? L("Password", "পাসওয়ার্ড") : "");
    var f = $("#ac-form"); if (d.activeElement && f.contains(d.activeElement) === false || !f._filled) { f.elements.name.value = p.name || u.name || ""; f.elements.phone.value = p.phone || ""; f.elements.address.value = p.address || ""; f._filled = true; }
    f.elements.email.value = u.email || "";
    fillSecurity();
    if (!acctWired) {
      acctWired = true;
      showPane((location.hash || "").slice(1));
      d.querySelectorAll(".ac-nav button").forEach(function (b) { b.onclick = function () { showPane(b.dataset.pane); window.scrollTo({ top: $(".ac-layout").offsetTop - 70, behavior: "smooth" }); }; });
      d.querySelectorAll("[data-goto]").forEach(function (b) { b.onclick = function () { showPane(b.dataset.goto); }; });
      window.addEventListener("hashchange", function () { showPane((location.hash || "").slice(1)); });
      f.addEventListener("submit", function (e) { e.preventDefault(); var m = $("#ac-msg"); if (!f.elements.name.value.trim()) { m.className = "auth-msg err"; m.textContent = L("Name is required.", "নাম দিতে হবে।"); return; } api.saveProfile({ name: f.elements.name.value.trim(), phone: f.elements.phone.value.trim(), address: f.elements.address.value.trim() }).then(function () { m.className = "auth-msg ok"; m.textContent = L("Saved.", "সেভ হয়েছে।"); }, function () { m.className = "auth-msg err"; m.textContent = L("Could not save. Try again.", "সেভ হয়নি। আবার চেষ্টা করুন।"); }); });
      $("#ac-out").onclick = function () { api.signOut().then(function () { location.href = "../index.html"; }); };
      $("#ac-ver").onclick = function () { var b = this; api.verifyEmail().then(function () { b.textContent = L("Link sent", "লিংক পাঠানো হয়েছে"); }, function (e) { alert(errMsg(e)); }); };
      $("#ac-ver-chk").onclick = function () { api.refreshUser().then(function () { if (!api.user.verified) alert(L("Not verified yet. Open the link in your email first.", "এখনো ভেরিফাই হয়নি। আগে ইমেইলের লিংকটি খুলুন।")); }); };
      $("#ac-export").onclick = function () { api.exportMine().then(function (x) { download("shunchi-my-data.json", x); }); };
      $("#ac-del").onclick = function () { if (!confirm(L("Delete your account and all saved data? This cannot be undone.", "অ্যাকাউন্ট ও সব সেভ করা ডেটা ডিলিট করবেন? এটি আর ফেরানো যাবে না।"))) return; api.deleteAccount().then(function () { location.href = "../index.html"; }, function (e) { alert(errMsg(e)); }); };
      $("#ai-new").onclick = openIdeaForm; $("#ai-cancel").onclick = function () { $("#ai-form").hidden = true; };
      $("#ai-form").addEventListener("submit", function (e) {
        e.preventDefault(); var fm = e.target, m = $("#ai-msg"), pr = api.profile || {}, title = fm.elements.title.value.trim(), det = fm.elements.details.value.trim();
        var say = function (t, ok) { m.className = "auth-msg " + (ok ? "ok" : "err"); m.textContent = t; };
        if (!title || !det) { say(L("Add the idea name and what it should do.", "আইডিয়ার নাম ও কী কাজ করবে লিখুন।")); return; }
        if (!/^[0-9+()\-\s]{6,30}$/.test(pr.phone || "")) { say(L("Your phone number in Profile looks invalid.", "প্রোফাইলের ফোন নম্বরটি সঠিক নয়।")); return; }
        if (!window.SHIdea) { say(L("Could not send. Reload and try again.", "পাঠানো যায়নি। রিলোড করে আবার চেষ্টা করুন।")); return; }
        var btn = fm.querySelector("[type=submit]"); btn.disabled = true; say(L("Sending…", "পাঠানো হচ্ছে…"), true);
        window.SHIdea.send({ type: fm.elements.type.value, title: title, details: det, name: pr.name || api.user.name, email: api.user.email, phone: pr.phone, address: pr.address }).then(function (r) {
          return api.addIdea({ track: r.code, title: title, details: det, type: fm.elements.type.value }).then(function () { fm.reset(); fm.hidden = true; m.textContent = ""; toast(L("Idea sent. Tracking number ", "আইডিয়া পাঠানো হয়েছে। ট্র্যাকিং নম্বর ") + r.code); loadLists(); });
        }, function () { say(L("Could not send right now. Try again in a moment.", "এখন পাঠানো যায়নি। একটু পরে আবার চেষ্টা করুন।")); }).then(function () { btn.disabled = false; });
      });
      $("#pw-form").addEventListener("submit", function (e) {
        e.preventDefault(); var fm = e.target, m = $("#pw-msg"), pw = fm.elements.pw.value, say = function (t, ok) { m.className = "auth-msg " + (ok ? "ok" : "err"); m.textContent = t; };
        if (pw.length < 6) { say(L("Password must be at least 6 characters.", "পাসওয়ার্ড কমপক্ষে ৬ অক্ষর হতে হবে।")); return; }
        if (pw !== fm.elements.pw2.value) { say(L("The two passwords do not match.", "দুটি পাসওয়ার্ড মেলেনি।")); return; }
        if (api.hasPassword() && !fm.elements.cur.value) { /* Firebase asks for a fresh login only when needed; try without first */ }
        var btn = $("#pw-go"); btn.disabled = true; say(L("Saving…", "সেভ হচ্ছে…"), true);
        api.setPassword(pw, fm.elements.cur.value).then(function () { fm.reset(); say(L("Password saved. You can now log in with your email and this password.", "পাসওয়ার্ড সেভ হয়েছে। এখন ইমেইল ও এই পাসওয়ার্ড দিয়ে লগইন করতে পারবেন।"), true); fillSecurity(); }, function (er) { say(errMsg(er)); }).then(function () { btn.disabled = false; });
      });
      loadLists();
    }
  }
  function toast(t) { var el = $("#sh-toast"); if (!el) { el = d.createElement("div"); el.id = "sh-toast"; el.className = "sh-toast"; d.body.appendChild(el); } el.textContent = t; el.classList.add("on"); clearTimeout(toast._t); toast._t = setTimeout(function () { el.classList.remove("on"); }, 5000); }
  function blockedNote() {
    var t = L("Your account is blocked, so you cannot comment or save data. Contact support if this is a mistake.", "আপনার অ্যাকাউন্ট ব্লক করা আছে, তাই মন্তব্য বা ডেটা সেভ করা যাবে না। ভুল হলে যোগাযোগ করুন।");
    d.querySelectorAll("#c-form,#acct-body .ac-hero").forEach(function (el) { var n = el.parentNode.querySelector(".blocked-note"); if (api.blocked) { if (!n) { n = d.createElement("p"); n.className = "blocked-note"; el.parentNode.insertBefore(n, el); } n.textContent = t; } else if (n) n.remove(); });
    var f = $("#c-form"); if (f && api.blocked) f.hidden = true;
  }
  function verifyHooks() {
    var rs = $("#c-resend"), rc = $("#c-recheck"); if (!rs || rs._w) return; rs._w = true;
    rs.onclick = function () { var b = rs; b.disabled = true; api.verifyEmail().then(function () { toast(L("Verification link sent. Check your inbox.", "ভেরিফিকেশন লিংক পাঠানো হয়েছে। ইনবক্স দেখুন।")); }, function () { toast(L("Try again in a minute.", "এক মিনিট পরে আবার চেষ্টা করুন।")); }).then(function () { setTimeout(function () { b.disabled = false; }, 20000); }); };
    rc.onclick = function () { api.refreshUser().then(function () { if (api.user && api.user.verified) comments(); else toast(L("Not verified yet.", "এখনো ভেরিফাই হয়নি।")); }); };
  }
  function pageHooks() { ideaForm(); comments(); account(); blockedNote(); verifyHooks(); }

  /* ---------- boot ---------- */
  function boot() {
    var b = $("#acct-btn"), mb = $("#acct-btn-m");
    getCfg().then(function (c) {
      if (!c) return;   // accounts are off until the Firebase config is filled in
      d.documentElement.classList.add("auth-on");
      [b, mb].forEach(function (x) { if (x) { x.hidden = false; x.addEventListener("click", function (e) { e.preventDefault(); if (!api.user) api.open("login"); else if (x.id === "acct-btn") toggleMenu(); else location.href = acctUrl("profile"); }); } });
      var need = false; try { need = !!localStorage.getItem(hint); } catch (e) {}
      if (need || $("[data-needs-auth]")) load().catch(function () {}); else render();
      d.querySelectorAll("[data-open-auth]").forEach(function (x) { x.addEventListener("click", function () { api.open(x.dataset.openAuth); }); });
      d.querySelectorAll(".lang button").forEach(function (x) { x.addEventListener("click", function () { setTimeout(render, 30); }); });
    });
  }
  if (d.readyState === "loading") d.addEventListener("DOMContentLoaded", boot); else boot();
})();
