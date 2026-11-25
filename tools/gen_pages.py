"""Generates every static page of the SHUNCHi website (home, apps, tools, blog, software pages, sitemap, feed).
Run from the repo root:  python3 -I tools/gen_pages.py site
Reads: site/assets/catalog.js (tools), site/data/apps.json (software), content/blog/*.md (blog posts)."""
import sys, os, re, json, html, subprocess, datetime
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SITE = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else os.path.join(ROOT, "site")
DOMAIN = "https://shunchiai.com"
TODAY = datetime.date.today().isoformat()
SITEMAP = []   # (path, lastmod, priority) of every page that should be in the sitemap

def esc(x): return html.escape(x, quote=True)
def jld(obj): return '<script type="application/ld+json">' + json.dumps(obj, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/") + "</script>"

_cat = json.loads(subprocess.run(["node", os.path.join(HERE, "dump_catalog.js"), SITE], capture_output=True, text=True, check=True).stdout)
CATS, APPS_BASE, TOOLS = _cat["CATS"], _cat["APPS"], _cat["TOOLS"]
try: CONFIG = json.load(open(os.path.join(HERE, "site_config.json"), encoding="utf-8"))
except Exception: CONFIG = {}
GTM_ID = os.environ.get("GTM_ID") or CONFIG.get("gtm_id", "")

# Latest released version comes from update.json (written by the release workflow). Nothing in the site hard-codes a version.
try: LATEST_VER = str(json.load(open(os.path.join(SITE, "update.json"), encoding="utf-8")).get("latest_version", "")).strip()
except Exception: LATEST_VER = ""
if GTM_ID and not re.fullmatch(r"GTM-[A-Z0-9]{4,10}", GTM_ID): raise SystemExit("gtm_id must look like GTM-XXXXXXX")
GTM_HEAD = ("<script>(function(w,d,s,l,i){w[l]=w[l]||[];w[l].push({'gtm.start':new Date().getTime(),event:'gtm.js'});var f=d.getElementsByTagName(s)[0],j=d.createElement(s),dl=l!='dataLayer'?'&l='+l:'';j.async=true;j.src='https://www.googletagmanager.com/gtm.js?id='+i+dl;f.parentNode.insertBefore(j,f);})(window,document,'script','dataLayer','" + GTM_ID + "');</script>\n") if GTM_ID else ""
GTM_BODY = ('<noscript><iframe src="https://www.googletagmanager.com/ns.html?id=' + GTM_ID + '" height="0" width="0" style="display:none;visibility:hidden"></iframe></noscript>\n') if GTM_ID else ""
try: APPS_JSON = json.load(open(os.path.join(SITE, "data", "apps.json"), encoding="utf-8")) or []
except Exception: APPS_JSON = []

try: VIDEOS_JSON = [v for v in (json.load(open(os.path.join(SITE, "data", "videos.json"), encoding="utf-8")) or []) if re.fullmatch(r"[A-Za-z0-9_-]{11}", str(v.get("id", "")))]
except Exception: VIDEOS_JSON = []

FONTS = ('<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
         '<link href="https://fonts.googleapis.com/css2?family=Anek+Bangla:wght@400;500;600;700;800&family=DM+Sans:wght@400;500;600;700;800&display=swap" rel="stylesheet">')

ICON_MENU = ('<svg class="bars" viewBox="0 0 24 24" aria-hidden="true"><path d="M4 7h16M4 12h16M4 17h16"/></svg>'
             '<svg class="x" viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18"/></svg>')

_OLD_LD = '''<script type="application/ld+json">{"@context":"https://schema.org","@type":"SoftwareApplication","name":"SHUNCHi","operatingSystem":"Windows 10, Windows 11","applicationCategory":"UtilitiesApplication","description":"Free AI voice typing for Bangla and English on Windows.","offers":{"@type":"Offer","price":"0","priceCurrency":"USD"},"author":{"@type":"Person","name":"Ruhul Amin"},"url":"https://shunchiai.com/"}</script>'''

def head(P, title, desc, path, extra="", robots="index,follow,max-image-preview:large,max-snippet:-1", og_type="website", img=None, ld=None):
    t, d = esc(title), esc(desc)
    img = img or f"{DOMAIN}/assets/og-cover.jpg"
    url = f"{DOMAIN}/{path}"
    ldtxt = "".join(jld(x) for x in (ld or []))
    return f'''<!DOCTYPE html>
<html lang="bn">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
{GTM_HEAD}<script>try{{var l=localStorage.getItem("shunchi-lang");document.documentElement.lang=l==="en"?"en":"bn"}}catch(e){{}}try{{var t=localStorage.getItem("theme");if(t==="dark"||t==="light")document.documentElement.setAttribute("data-theme",t)}}catch(e){{}}</script>
<meta name="theme-color" content="#F8FAFD" media="(prefers-color-scheme: light)">
<meta name="theme-color" content="#0A1222" media="(prefers-color-scheme: dark)">
<title>{t}</title>
<meta name="description" content="{d}">
<meta name="robots" content="{robots}">
<meta name="author" content="Ruhul Amin">
<link rel="canonical" href="{url}">
<link rel="alternate" type="application/rss+xml" title="SHUNCHi blog" href="{DOMAIN}/feed.xml">
<meta property="og:type" content="{og_type}"><meta property="og:site_name" content="SHUNCHi"><meta property="og:locale" content="en_US"><meta property="og:locale:alternate" content="bn_BD">
<meta property="og:title" content="{t}"><meta property="og:description" content="{d}">
<meta property="og:url" content="{url}"><meta property="og:image" content="{img}">
<meta name="twitter:card" content="summary_large_image"><meta name="twitter:title" content="{t}"><meta name="twitter:description" content="{d}"><meta name="twitter:image" content="{img}">
<link rel="icon" type="image/png" href="{P}assets/favicon.png"><link rel="apple-touch-icon" href="{P}assets/apple-touch-icon.png">
{FONTS}
<link rel="manifest" href="{P}manifest.webmanifest"><meta name="mobile-web-app-capable" content="yes"><meta name="apple-mobile-web-app-capable" content="yes"><meta name="apple-mobile-web-app-title" content="SHUNCHi">
<link rel="stylesheet" href="{P}assets/site.css?v=20">
{extra}{ldtxt}</head>
<body>
{GTM_BODY}<a class="skip" href="#main"><span class="en">Skip to content</span><span class="bn">মূল অংশে যান</span></a>
'''

def header(P, current=""):
    def a(href, en, bn, key):
        cur = ' aria-current="page"' if current == key else ""
        return f'<a href="{href}"{cur}><span class="en">{en}</span><span class="bn">{bn}</span></a>'
    items = [
        (f"{P}index.html#features", "Features", "সুবিধা", "f"),
        (f"{P}index.html#setup", "Setup", "সেটআপ", "s"),
        (f"{P}apps/index.html", "More Apps", "আরও অ্যাপ", "apps"),
        (f"{P}blog/index.html", "Blog", "ব্লগ", "blog"),
        (f"{P}index.html#faq", "FAQ", "প্রশ্নোত্তর", "q"),
        (f"{P}index.html#developer", "Developer", "ডেভেলপার", "d"),
    ]
    links = "".join(a(*i) for i in items)
    menu = "".join(f'<a class="item" href="{h}"><span class="en">{e}</span><span class="bn">{b}</span></a>' for h, e, b, _ in items)
    lang = ('<div class="lang" role="group" aria-label="Language"><button type="button" data-lang="en" aria-pressed="true">EN</button>'
            '<button type="button" data-lang="bn" aria-pressed="false">বাংলা</button></div>')
    return f'''<header class="site-header">
  <div class="wrap bar">
    <a class="brand" href="{P}index.html" aria-label="SHUNCHi home"><img src="{P}assets/shunchi-logo.png" alt="SHUNCHi" width="96" height="36"></a>
    <nav class="links" aria-label="Main">{links}</nav>
    <div class="actions">{lang}<button class="theme-btn" id="theme-btn" type="button" aria-label="Toggle dark mode" title="Dark / Light"><svg class="i-moon" viewBox="0 0 24 24" aria-hidden="true"><path d="M20 14.5A8 8 0 0 1 9.5 4 8.5 8.5 0 1 0 20 14.5z"/></svg><svg class="i-sun" viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M2 12h2M20 12h2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M19.1 4.9l-1.4 1.4M6.3 17.7l-1.4 1.4"/></svg></button>
      <a class="btn btn-primary btn-sm" href="{P}download/index.html"><span class="en">Download</span><span class="bn">ডাউনলোড</span></a>
      <button class="menu-btn" id="menu-btn" type="button" aria-expanded="false" aria-controls="menu-panel" aria-label="Menu">{ICON_MENU}</button>
    </div>
  </div>
  <div class="menu-panel" id="menu-panel"><nav aria-label="Mobile">{menu}</nav>
    <a class="btn btn-primary" href="{P}download/index.html"><span class="en">Download for Windows</span><span class="bn">উইন্ডোজের জন্য ডাউনলোড</span></a></div>
</header>
'''

def footer(P):
    def l(href, en, bn=None, ext=False):
        lab = f'<span class="en">{en}</span><span class="bn">{bn}</span>' if bn else en
        return f'<a href="{href}"' + (' rel="noopener"' if ext else '') + f'>{lab}</a>'
    links = "".join([
        l(f"{P}index.html#features","Features","সুবিধা"),
        l(f"{P}index.html#setup","Setup","সেটআপ"),
        l(f"{P}index.html#faq","FAQ","প্রশ্নোত্তর"),
        l(f"{P}download/index.html","Download","ডাউনলোড"),
        l(f"{P}apps/index.html","Apps","অ্যাপ ও টুল"),
        l(f"{P}blog/index.html","Blog","ব্লগ"),
        l(f"{P}index.html#developer","Developer","ডেভেলপার"),
        l(f"{P}privacy.html","Privacy","গোপনীয়তা"),
        l("https://www.facebook.com/voice.shunchi","Facebook",ext=True),
        l("https://www.instagram.com/voice.shunchi/","Instagram",ext=True),
        l("mailto:voice.shunchi@gmail.com","Email"),
    ])
    return f'''<footer class="site-footer">
  <div class="wrap">
    <div class="foot-top">
      <img src="{P}assets/shunchi-logo.png" alt="SHUNCHi" width="90" height="34">
      <p><span class="en">Free AI voice typing for Windows. You speak, we write.</span><span class="bn">উইন্ডোজের জন্য ফ্রি এআই ভয়েস টাইপিং। আপনি বলুন, আমরা লিখি।</span></p>
    </div>
    <nav class="foot-links" aria-label="Footer">{links}</nav>
    <div class="legal"><span>© <span id="year">2026</span> SHUNCHi · Ruhul Amin</span>
      <span><span class="en">Made in Bangladesh</span><span class="bn">বাংলাদেশে তৈরি</span></span></div>
  </div>
</footer>
''' + tabbar(P)


def tabbar(P):
    def t(href, key, en, bn, svg):
        return (f'<a href="{href}" data-tab="{key}"><svg viewBox="0 0 24 24" aria-hidden="true">{svg}</svg>'
                f'<span class="en">{en}</span><span class="bn">{bn}</span></a>')
    return ('<nav class="tabbar" aria-label="App navigation">'
      + t(f"{P}index.html", "home", "Home", "হোম", '<path d="M4 11l8-7 8 7v8a1 1 0 0 1-1 1h-4v-6H9v6H5a1 1 0 0 1-1-1z"/>')
      + t(f"{P}index.html#setup", "setup", "Setup", "সেটআপ", '<circle cx="12" cy="12" r="3"/><path d="M12 3v3M12 18v3M3 12h3M18 12h3M5.6 5.6l2.1 2.1M16.3 16.3l2.1 2.1M18.4 5.6l-2.1 2.1M7.7 16.3l-2.1 2.1"/>')
      + t(f"{P}apps/index.html", "apps", "Apps", "অ্যাপ", '<rect x="4" y="4" width="7" height="7" rx="2"/><rect x="13" y="4" width="7" height="7" rx="2"/><rect x="4" y="13" width="7" height="7" rx="2"/><rect x="13" y="13" width="7" height="7" rx="2"/>')
      + t(f"{P}blog/index.html", "blog", "Blog", "ব্লগ", '<path d="M5 4h11l3 3v13H5z"/><path d="M8 10h8M8 14h8M8 17h5"/>')
      + t(f"{P}index.html#faq", "faq", "FAQ", "প্রশ্ন", '<circle cx="12" cy="12" r="9"/><path d="M9.5 9.5a2.5 2.5 0 1 1 3.5 2.3c-.7.4-1 .9-1 1.7M12 17v.01"/>')
      + t(f"{P}index.html#developer", "dev", "Dev. Info", "ডেভ ইনফো", '<circle cx="12" cy="8" r="3.5"/><path d="M5 20c0-3.6 3-6 7-6s7 2.4 7 6"/>')
      + t(f"{P}download/index.html", "download", "Download", "ডাউনলোড", '<path d="M12 4v11M7 11l5 5 5-5M5 20h14"/>')
      + '</nav>\n')


SUGGEST_FORM = '''<div class="idea-box" id="suggest">
  <div class="suggest-head">
    <div class="suggest-ico" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="M9 18h6M10 21h4M12 3a6 6 0 0 0-3.5 10.9c.6.5 1 1.2 1 2.1h5c0-.9.4-1.6 1-2.1A6 6 0 0 0 12 3z"/></svg></div>
    <div><h3><span class="en">Suggest an app or tool</span><span class="bn">অ্যাপ বা টুলের আইডিয়া দিন</span></h3>
    <p><span class="en">Tell me what you need. The ideas people ask for most get built first.</span><span class="bn">কী দরকার জানান। সবচেয়ে বেশি চাওয়া আইডিয়াগুলো আগে বানানো হবে।</span></p></div>
  </div>
  <form class="suggest-form" id="suggest-form" novalidate>
    <input type="text" name="_honey" tabindex="-1" autocomplete="off" class="hp" aria-hidden="true">
    <label class="f"><span class="lab"><span class="en">I want a</span><span class="bn">আমি চাই</span></span>
      <select name="type"><option value="Free tool">Free web tool · ফ্রি ওয়েব টুল</option><option value="Windows app">Windows app · উইন্ডোজ অ্যাপ</option><option value="SHUNCHi feature">SHUNCHi feature · SHUNCHi-র নতুন ফিচার</option><option value="Other">Other · অন্যকিছু</option></select></label>
    <label class="f"><span class="lab"><span class="en">Idea name</span><span class="bn">আইডিয়ার নাম</span></span>
      <input type="text" name="title" maxlength="80" required></label>
    <label class="f full"><span class="lab"><span class="en">What should it do?</span><span class="bn">এটি কী কাজ করবে?</span></span>
      <textarea name="details" rows="4" maxlength="1200" required></textarea></label>
    <label class="f"><span class="lab"><span class="en">Your name (optional)</span><span class="bn">আপনার নাম (ঐচ্ছিক)</span></span>
      <input type="text" name="name" maxlength="60" autocomplete="name"></label>
    <label class="f"><span class="lab"><span class="en">Email or phone (optional)</span><span class="bn">ইমেইল বা ফোন (ঐচ্ছিক)</span></span>
      <input type="text" name="contact" maxlength="80" autocomplete="email"></label>
    <div class="full suggest-act">
      <button class="btn btn-primary" type="submit"><span class="en">Send my idea</span><span class="bn">আইডিয়া পাঠান</span></button>
      <p class="suggest-msg" id="suggest-msg" role="status" aria-live="polite"></p>
    </div>
  </form>
</div>'''

def reg(path, prio="0.7", freq="monthly", lastmod=None):
    """Put a page in the sitemap. path is the public path, e.g. '' (home), 'apps/', 'blog/my-post.html'."""
    SITEMAP.append((path, lastmod or TODAY, prio, freq))

def crumbs_ld(items):
    return {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": i + 1, "name": n, "item": f"{DOMAIN}/{p}"} for i, (n, p) in enumerate(items)]}

# ---------------------------------------------------------------- static (crawlable) lists
# The same cards are drawn again by assets/catalog.js in the browser; these copies let search engines read them without running JS.
def bi(en, bn): return f'<span class="en">{esc(en)}</span><span class="bn">{esc(bn or en)}</span>'
STATUS_TXT = {"live": ("Live", "চালু"), "next": ("Next up", "পরবর্তী"), "soon": ("Planned", "পরিকল্পনায়")}
def cat_of(k): return next((c for c in CATS if c["k"] == k), None)
def tool_static(t):
    c = cat_of(t["c"]); st = STATUS_TXT.get(t["s"], STATUS_TXT["soon"])
    return (f'<div class="tool"><div class="tool-body"><h3>{bi(t["t"], t["tb"])}</h3><p>{bi(t["d"], t["db"])}</p></div>'
            f'<div class="tool-foot"><span class="tool-cat">{bi(c["en"], c["bn"]) if c else ""}</span><span class="badge {"live" if t["s"]=="live" else ("next" if t["s"]=="next" else "")}">{bi(*st)}</span></div></div>')
def tools_static(ids=None, grouped=False):
    lst = [t for i in ids for t in TOOLS if t["id"] == i] if ids else sorted(TOOLS, key=lambda t: {"live": 0, "next": 1}.get(t["s"], 2))
    if not grouped: return '<div class="tools">' + "".join(tool_static(t) for t in lst) + "</div>"
    out = []
    for c in CATS:
        items = [t for t in lst if t["c"] == c["k"]]
        if items: out.append(f'<section class="cat-block" id="cat-{c["k"]}"><div class="cat-head"><h3>{bi(c["en"], c["bn"])}</h3><span class="cat-count">{len(items)}</span></div>'
                             f'<p class="cat-desc">{bi(c["de"], c["db"])}</p><div class="tools">' + "".join(tool_static(t) for t in items) + "</div></section>")
    return "".join(out)
def apps_all():
    rows = [dict(a, _more="index.html", _dl="download/index.html") for a in APPS_BASE[:1]]
    for a in APPS_JSON:
        if a.get("status", "live") == "live" and a.get("id") and a.get("name"):
            rows.append({"name": a["name"], "en": a.get("tagline_en") or a.get("tagline") or "", "bn": a.get("tagline_bn") or a.get("tagline_en") or "",
                         "badge": a.get("version", ""), "logo": a.get("logo", ""), "_more": f"apps/{a['id']}.html", "_dl": a.get("url", "")})
    return rows
def apps_static(P, limit=None):
    out = []
    for a in apps_all()[:limit]:
        logo = f'<img src="{P}{a["logo"]}" alt="" width="52" height="52">' if a.get("logo") else esc(a["name"][:1].upper())
        out.append(f'<div class="app-row"><div class="app-tile">{logo}</div><div class="app-body"><h3>{esc(a["name"])}'
                   f'{"<span class=ver>"+esc(a["badge"])+"</span>" if a.get("badge") else ""}</h3><p>{bi(a["en"], a["bn"])}</p></div>'
                   f'<div class="app-act"><a class="btn btn-primary btn-sm" href="{(P+a["_dl"]) if not a["_dl"].startswith("http") else a["_dl"]}">{bi("Download", "ডাউনলোড")}</a>'
                   f'<a class="btn btn-ghost btn-sm" href="{P}{a["_more"]}">{bi("Details", "বিস্তারিত")}</a></div></div>')
    return "".join(out)

# ---------------------------------------------------------------- blog (content/blog/*.md)
import markdown as _md
def parse_post(path):
    raw = open(path, encoding="utf-8").read().replace("\r\n", "\n")
    meta, body = {}, raw
    if raw.startswith("---\n"):
        end = raw.find("\n---", 4)
        if end > 0:
            for line in raw[4:end].split("\n"):
                if ":" in line:
                    k, v = line.split(":", 1); meta[k.strip().lower()] = v.strip().strip('"').strip("'")
            body = raw[end + 4:].lstrip("\n")
    slug = meta.get("slug") or os.path.splitext(os.path.basename(path))[0]
    slug = re.sub(r"[^a-z0-9-]+", "-", slug.lower()).strip("-")
    text = re.sub(r"[#*_`>\[\]()!-]", " ", body)
    words = len(text.split())
    lang = meta.get("lang", "en")
    md = _md.Markdown(extensions=["extra", "sane_lists", "toc"], extension_configs={"toc": {"permalink": False}})
    return {"slug": slug, "title": meta.get("title", slug), "desc": meta.get("description", ""), "date": meta.get("date", TODAY),
            "updated": meta.get("updated", meta.get("date", TODAY)), "lang": lang, "tags": [t.strip() for t in meta.get("tags", "").split(",") if t.strip()],
            "cover": meta.get("cover", ""), "draft": meta.get("draft", "").lower() in ("1", "true", "yes"), "html": md.convert(body).replace("<img ", '<img loading="lazy" decoding="async" '),
            "mins": max(1, round(words / (170 if lang == "bn" else 220)))}
POSTS = []
_bd = os.path.join(ROOT, "content", "blog")
if os.path.isdir(_bd):
    for f in sorted(os.listdir(_bd)):
        if f.endswith(".md"):
            pp = parse_post(os.path.join(_bd, f))
            if not pp["draft"]: POSTS.append(pp)
POSTS.sort(key=lambda x: x["date"], reverse=True)
BN_DIGITS = str.maketrans("0123456789", "০১২৩৪৫৬৭৮৯")
def nice_date(d, lang="en"):
    try:
        dt = datetime.date.fromisoformat(d)
        if lang == "bn":
            mons = ["জানুয়ারি","ফেব্রুয়ারি","মার্চ","এপ্রিল","মে","জুন","জুলাই","আগস্ট","সেপ্টেম্বর","অক্টোবর","নভেম্বর","ডিসেম্বর"]
            return f"{dt.day} {mons[dt.month-1]} {dt.year}".translate(BN_DIGITS)
        return dt.strftime("%d %b %Y").lstrip("0")
    except Exception: return d
def post_card(p, P):
    mins = f"{p['mins']} মিনিট পড়া".translate(BN_DIGITS) if p["lang"] == "bn" else f"{p['mins']} min read"
    cover = f'<img class="post-thumb" src="{P}{p["cover"]}" alt="" loading="lazy" width="640" height="336">' if p["cover"] else ""
    return (f'<a class="post-card" href="{P}blog/{p["slug"]}.html">{cover}<div class="post-card-body">'
            f'<div class="post-meta"><span class="tag lang-{p["lang"]}">{"বাংলা" if p["lang"]=="bn" else "English"}</span><span>{nice_date(p["date"], p["lang"])}</span><span>{mins}</span></div>'
            f'<h3 lang="{p["lang"]}">{esc(p["title"])}</h3><p lang="{p["lang"]}">{esc(p["desc"])}</p></div></a>')

def write(path, text):
    full = os.path.join(SITE, path)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    open(full, "w", encoding="utf-8").write(text)


# ---------------------------------------------------------------- setup videos (YouTube links added in the admin panel)
def video_card(v):
    vid = v["id"]; te = esc(v.get("title_en") or v.get("title_bn") or "Video"); tb = esc(v.get("title_bn") or v.get("title_en") or "")
    return (f'<figure class="vid"><a class="vid-thumb" href="https://www.youtube.com/watch?v={vid}" data-vid="{vid}" target="_blank" rel="noopener" aria-label="Play: {te}">'
            f'<img src="https://i.ytimg.com/vi/{vid}/hqdefault.jpg" alt="" loading="lazy" width="480" height="360">'
            '<span class="vid-play" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg></span></a>'
            f'<figcaption><span class="en">{te}</span><span class="bn">{tb}</span></figcaption></figure>')

def videos_block(P, limit=3):
    if not VIDEOS_JSON: return ""
    shown = VIDEOS_JSON[:limit]
    return (f'<div class="wrap vids-wrap" id="videos"><div class="head"><div class="eyebrow"><span class="en">Video guide</span><span class="bn">ভিডিও গাইড</span></div>'
            '<h2><span class="en">Watch how to set it up</span><span class="bn">দেখে দেখে সেটআপ করুন</span></h2></div>'
            f'<div class="vids" data-n="{len(shown)}">' + "".join(video_card(v) for v in shown) + '</div>'
            f'<p class="vids-more"><a class="btn btn-ghost" href="{P}videos/index.html"><span class="en">View all videos</span><span class="bn">সব ভিডিও দেখুন</span> <span aria-hidden="true">→</span></a></p></div>')

# ====================================================================== HOME
FAQ_ITEMS = []
def q(en, bn, ae, ab):
    FAQ_ITEMS.append((en, re.sub(r"<[^>]+>", "", ae).strip()))
    return (f'<details><summary><span class="en">{en}</span><span class="bn">{bn}</span></summary><div class="ans">'
            f'<div class="en">{ae}</div><div class="bn">{ab}</div></div></details>')

faq = "".join([
    q("Is SHUNCHi really free?", "SHUNCHi কি সত্যিই ফ্রি?",
      "<p>Yes. The app is free. It uses your own Gemini API key, and Google's free tier has daily limits. If you reach the limit, SHUNCHi tells you and works again after it resets.</p>",
      "<p>হ্যাঁ, অ্যাপটি সম্পূর্ণ ফ্রি। এটি আপনার নিজের Gemini API কী ব্যবহার করে, আর গুগলের ফ্রি টিয়ারে দৈনিক একটা সীমা আছে। সীমা শেষ হলে SHUNCHi আপনাকে জানায় এবং রিসেটের পর আবার চলে।</p>"),
    q("Do I need a microphone?", "আমার কি মাইক্রোফোন লাগবে?",
      "<p>Yes, SHUNCHi listens through a microphone. Most laptops have one built in, so you need nothing extra. A desktop computer usually has none, so plug in a microphone or a headset (USB or 3.5 mm).</p>",
      "<p>হ্যাঁ, SHUNCHi মাইক্রোফোনের মাধ্যমে আপনার কথা শোনে। বেশিরভাগ ল্যাপটপে মাইক্রোফোন বিল্ট-ইন থাকে, তাই আলাদা কিছু লাগে না। ডেস্কটপ কম্পিউটারে সাধারণত থাকে না, তাই একটি মাইক্রোফোন বা হেডসেট (USB বা ৩.৫ মিমি) লাগাতে হবে।</p>"),
    q("Nothing happens when I press the shortcut", "শর্টকাট চাপলে কিছুই হয় না",
      "<p>Check that SHUNCHi is running (its icon sits in the system tray) and that Settings shows <b>Connected</b> next to your key. Press the left Win key together with the left Ctrl or left Shift key.</p>",
      "<p>SHUNCHi চলছে কিনা দেখুন (সিস্টেম ট্রেতে এর আইকন থাকে) এবং Settings-এ কী-র পাশে <b>Connected</b> লেখা আছে কিনা মিলিয়ে নিন। বাঁ পাশের Win কী-র সাথে বাঁ Ctrl বা বাঁ Shift একসাথে চাপুন।</p>"),
    q("It says it did not hear anything", "“কিছু শোনা যায়নি” বলছে",
      "<p>Open Windows Settings, then Privacy, then Microphone, and allow desktop apps to use the microphone. Then choose the right input under Microphone in SHUNCHi Settings and speak a little closer.</p>",
      "<p>Windows Settings > Privacy > Microphone-এ গিয়ে ডেস্কটপ অ্যাপকে মাইক্রোফোন ব্যবহারের অনুমতি দিন। এরপর SHUNCHi-র Settings-এর Microphone অংশ থেকে সঠিক ইনপুট বেছে নিন এবং মাইকের একটু কাছে বলুন।</p>"),
    q("The text is copied but not typed", "লেখা কপি হয় কিন্তু বসে না",
      "<p>Programs running as administrator can block automatic typing. SHUNCHi keeps the text on your clipboard, so press Ctrl + V.</p>",
      "<p>অ্যাডমিন হিসেবে চলা প্রোগ্রাম স্বয়ংক্রিয় টাইপিং আটকে দিতে পারে। লেখাটি আপনার ক্লিপবোর্ডে থেকে যায়, তাই Ctrl + V চাপুন।</p>"),
    q("My API key is rejected", "আমার API কী গ্রহণ করছে না",
      "<p>Copy the key again from Google AI Studio and make sure there are no spaces in it. A key is long and usually starts with “AIza”. Also check that the Gemini API is available in your country for that project.</p>",
      "<p>Google AI Studio থেকে কী আবার কপি করুন এবং মাঝে কোনো ফাঁকা জায়গা আছে কিনা দেখুন। কী বেশ লম্বা হয় এবং সাধারণত “AIza” দিয়ে শুরু হয়। কীটি যে প্রজেক্টের, সেখানে আপনার দেশে Gemini API চালু আছে কিনা তাও দেখে নিন।</p>"),
    q("Does it work offline?", "ইন্টারনেট ছাড়া কি চলে?",
      "<p>No. Your recording is sent to Google to be transcribed, so you need an internet connection. Without one, SHUNCHi shows a clear notice and keeps running.</p>",
      "<p>না। আপনার রেকর্ডিং লেখায় রূপান্তরের জন্য গুগলে পাঠানো হয়, তাই ইন্টারনেট লাগে। ইন্টারনেট না থাকলে SHUNCHi পরিষ্কার একটি বার্তা দেখায়, বন্ধ হয়ে যায় না।</p>"),
    q("What happens to my audio and my text?", "আমার অডিও আর লেখার কী হয়?",
      "<p>Audio goes to Google only to be transcribed, using your own key. On Google's free tier, content may be used to improve Google's products, so avoid dictating secrets. Your history stays on your computer and your key stays in Windows Credential Manager. Read the <a href=\"privacy.html\">privacy page</a>.</p>",
      "<p>অডিও শুধু লেখায় রূপান্তরের জন্য আপনার নিজের কী দিয়ে গুগলে যায়। গুগলের ফ্রি টিয়ারে কনটেন্ট তাদের পণ্যের উন্নয়নে ব্যবহৃত হতে পারে, তাই গোপন কিছু ডিকটেট না করাই ভালো। হিস্ট্রি থাকে শুধু আপনার কম্পিউটারে আর কী থাকে Windows Credential Manager-এ। বিস্তারিত <a href=\"privacy.html\">গোপনীয়তা পাতায়</a>।</p>"),
    q("How do I update or uninstall?", "কীভাবে আপডেট বা আনইনস্টল করব?",
      "<p>When a newer version is out, SHUNCHi shows a banner on its Dashboard with a Download button. Run the new installer over the old one; your settings and key are kept. To uninstall, use Windows Settings, then Apps.</p>",
      "<p>নতুন ভার্সন এলে SHUNCHi-র Dashboard-এ ডাউনলোড বাটনসহ একটি ব্যানার দেখা যায়। নতুন ইনস্টলার পুরনোটার ওপরেই চালান, সেটিংস ও কী অক্ষত থাকবে। আনইনস্টল করতে Windows Settings > Apps ব্যবহার করুন।</p>"),
])

SOCIAL_ICONS = {
    "fb": '<svg viewBox="0 0 24 24"><path d="M14 8h3V4h-3a4 4 0 0 0-4 4v3H7v4h3v6h4v-6h3l1-4h-4V8z"/></svg>',
    "ig": '<svg viewBox="0 0 24 24"><rect x="4" y="4" width="16" height="16" rx="5"/><circle cx="12" cy="12" r="3.5"/><path d="M17 7h.01"/></svg>',
    "in": '<svg viewBox="0 0 24 24"><rect x="4" y="4" width="16" height="16" rx="3"/><path d="M8 11v5M8 8h.01M12 16v-5M12 13a2 2 0 0 1 4 0v3"/></svg>',
    "mail": '<svg viewBox="0 0 24 24"><rect x="3" y="5" width="18" height="14" rx="3"/><path d="M4 8l8 6 8-6"/></svg>',
}

HOME_LD = [
    {"@context": "https://schema.org", "@type": "WebSite", "name": "SHUNCHi", "alternateName": "শুনছি", "url": DOMAIN + "/", "inLanguage": ["en", "bn"],
     "publisher": {"@type": "Person", "name": "Ruhul Amin"}},
    {"@context": "https://schema.org", "@type": "Organization", "name": "SHUNCHi", "url": DOMAIN + "/", "logo": DOMAIN + "/assets/icon-512.png",
     "email": "voice.shunchi@gmail.com", "founder": {"@type": "Person", "name": "Ruhul Amin"},
     "sameAs": ["https://www.facebook.com/voice.shunchi", "https://www.instagram.com/voice.shunchi/"]},
    {"@context": "https://schema.org", "@type": "SoftwareApplication", "name": "SHUNCHi", "alternateName": "শুনছি",
     "operatingSystem": "Windows 10, Windows 11", "applicationCategory": "UtilitiesApplication", **({"softwareVersion": LATEST_VER} if LATEST_VER else {}),
     "description": "Free AI voice typing for Bangla and English on Windows. Press a shortcut, speak, and the text is typed into any app.",
     "inLanguage": ["bn", "en"], "offers": {"@type": "Offer", "price": "0", "priceCurrency": "USD"},
     "author": {"@type": "Person", "name": "Ruhul Amin"}, "url": DOMAIN + "/", "downloadUrl": DOMAIN + "/download/"},
    {"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [
        {"@type": "Question", "name": qn, "acceptedAnswer": {"@type": "Answer", "text": an}} for qn, an in FAQ_ITEMS]},
]
HOME_TOOLS = ["build-cv","invoice-maker","pdf-tools","image-compressor","budget-calculator","tour-calculator","bangla-typing","qr-code","bijoy-unicode"]
reg("", "1.0", "weekly")
home = head("", "SHUNCHi (শুনছি): Free Bangla and English Voice Typing for Windows",
            "Free AI voice typing app for Windows. Press a shortcut, speak Bangla or English, and the text is typed in any app. বাংলা ভয়েস টাইপিং।",
            "", ld=HOME_LD) + header("") + f'''
<main id="main">
<div class="hero"><div class="wrap hero-grid">
  <div>
    <div class="eyebrow"><span class="en">Free AI voice typing for Windows</span><span class="bn">উইন্ডোজের জন্য ফ্রি এআই ভয়েস টাইপিং</span> · by Ruhul Amin</div>
    <h1>You Speak,<br><em>We Write.</em></h1>
    <div class="tagline-bn"><p>লেখা হবে উন্মুক্ত, থাকবে না টাইপের কোনো বাধা।</p><p><strong>“আপনার কণ্ঠই হবে আপনার লেখা”</strong></p></div>
    <p class="lead"><span class="en">Press a shortcut, speak Bangla or English, then pause. SHUNCHi types the finished, punctuated text wherever your cursor is: a browser, WhatsApp, Word, anywhere.</span>
      <span class="bn">একটি শর্টকাট চাপুন, বাংলা বা ইংরেজিতে কথা বলুন, তারপর থামুন। ব্রাউজার, হোয়াটসঅ্যাপ বা ওয়ার্ড, কার্সর যেখানেই থাকুক, দাঁড়ি-কমাসহ গোছানো লেখা সেখানেই বসে যাবে।</span></p>
    <div class="cta">
      <a class="btn btn-primary" href="download/index.html"><span class="en">Download for Windows</span><span class="bn">উইন্ডোজের জন্য ডাউনলোড</span></a>
      <a class="btn btn-ghost" href="#setup"><span class="en">How to set up</span><span class="bn">কীভাবে সেটআপ করবেন</span></a>
    </div>
    <ul class="pills"><li><span class="en">Any language</span><span class="bn">যেকোনো ভাষা</span></li><li><span class="en">Auto punctuation</span><span class="bn">স্বয়ংক্রিয় দাঁড়ি-কমা</span></li><li><span class="en">100% Free</span><span class="bn">১০০% ফ্রি</span></li><li>Windows 10 / 11</li></ul>
    <div class="keys" aria-label="Shortcuts">
      <div class="keybox"><span class="label"><span class="en">Bangla</span><span class="bn">বাংলা</span></span><kbd>Win</kbd><span class="plus">+</span><kbd>Left Ctrl</kbd></div>
      <div class="keybox"><span class="label"><span class="en">English</span><span class="bn">ইংরেজি</span></span><kbd>Win</kbd><span class="plus">+</span><kbd>Left Shift</kbd></div>
    </div>
  </div>
  <div class="demo" aria-hidden="true" data-demo>
    <div class="demo-tabs"><span class="dt on" data-app="wa"><i></i>WhatsApp</span><span class="dt" data-app="ms"><i></i>Messenger</span><span class="dt" data-app="em"><i></i><span class="en">Email</span><span class="bn">ইমেইল</span></span><span class="dt" data-app="nt"><i></i><span class="en">Notes</span><span class="bn">নোটস</span></span></div>
    <div class="ds" data-skin="wa">
      <div class="ds-head"><span class="av">R</span><div><b class="ds-name"><span class="en">Rahim</span><span class="bn">রহিম</span></b><small class="ds-sub"><span class="en">online</span><span class="bn">অনলাইন</span></small></div></div>
      <div class="ds-msgs"></div>
      <div class="ds-input"><span class="typed"><span class="en">Hi Rahim, the files are ready. I will send them tonight.</span><span class="bn">রহিম ভাই, ফাইলগুলো তৈরি। আমি আজ রাতেই পাঠিয়ে দেব।</span></span><span class="caret"></span></div>
    </div>
    <div class="popup"><div class="popup-row">
      <div class="orb"><svg viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2" stroke-linecap="round"><rect x="9" y="3" width="6" height="11" rx="3" fill="#fff"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3"/></svg></div>
      <div class="wave"><b></b><b></b><b></b><b></b><b></b><b></b><b></b><b></b><b></b><b></b><b></b><b></b><b></b><b></b><b></b><b></b><b></b><b></b></div>
      <div class="timer">00:07</div></div>
      <div class="popup-foot"><span><span class="en">Listening · pause when you finish</span><span class="bn">শুনছি · শেষ হলে থামুন</span></span><span>Built by Ruhul Amin</span></div></div>
  </div>
</div></div>

<section id="features"><div class="wrap">
  <div class="head"><div class="eyebrow"><span class="en">Features</span><span class="bn">সুবিধা</span></div>
    <h2><span class="en">Simple on the surface, careful underneath</span><span class="bn">ব্যবহারে সহজ, ভেতরে যত্নে গড়া</span></h2></div>
  <ul class="rules">
    <li><h3><span class="en">Bangla and English</span><span class="bn">বাংলা ও ইংরেজি</span></h3><p><span class="en">One shortcut for each language. English words inside Bangla speech are written correctly too.</span><span class="bn">প্রতিটি ভাষার জন্য আলাদা শর্টকাট। বাংলা বলার মাঝে ইংরেজি শব্দ এলেও সেগুলো ঠিকভাবে লেখা হয়।</span></p></li>
    <li><h3><span class="en">Finished, punctuated text</span><span class="bn">দাঁড়ি-কমাসহ গোছানো লেখা</span></h3><p><span class="en">Smart mode adds punctuation, drops filler words and sets lists in order, so the text is ready to send.</span><span class="bn">স্মার্ট মোড দাঁড়ি-কমা বসায়, বাড়তি শব্দ বাদ দেয় এবং তালিকা সাজিয়ে দেয়। লেখাটি তাই সরাসরি পাঠানো যায়।</span></p></li>
    <li><h3><span class="en">Works in every app</span><span class="bn">সব অ্যাপে কাজ করে</span></h3><p><span class="en">The text is pasted at your cursor, so no plugin or extension is needed for any program.</span><span class="bn">লেখা কার্সরের জায়গায় বসে যায়, তাই কোনো প্রোগ্রামের জন্য আলাদা প্লাগইন বা এক্সটেনশন লাগে না।</span></p></li>
    <li><h3><span class="en">Stops by itself</span><span class="bn">নিজে থেকেই থামে</span></h3><p><span class="en">Stop talking and it finishes. It learns the sound of your room, so a fan or an AC does not confuse it.</span><span class="bn">কথা থামালেই রেকর্ডিং শেষ হয়। ঘরের আওয়াজ বুঝে নেয়, তাই ফ্যান বা এসির শব্দে আটকে থাকে না।</span></p></li>
    <li><h3><span class="en">Your key, your data</span><span class="bn">আপনার কী, আপনার তথ্য</span></h3><p><span class="en">You use your own free Gemini key, kept in Windows Credential Manager. Your history stays on your PC.</span><span class="bn">আপনি নিজের ফ্রি Gemini কী ব্যবহার করেন, যা থাকে Windows Credential Manager-এ। হিস্ট্রি থাকে শুধু আপনার পিসিতে।</span></p></li>
    <li><h3><span class="en">Told about updates</span><span class="bn">আপডেটের খবর পাবেন</span></h3><p><span class="en">When a new version is released, SHUNCHi tells you and links to the download.</span><span class="bn">নতুন ভার্সন এলে SHUNCHi নিজেই জানায় এবং ডাউনলোডের লিংক দেখায়।</span></p></li>
  </ul>
  <div class="head" style="margin:56px 0 28px"><div class="eyebrow"><span class="en">How it works</span><span class="bn">কীভাবে কাজ করে</span></div>
    <h2><span class="en">Three moves</span><span class="bn">তিনটি ধাপ</span></h2></div>
  <ol class="flow">
    <li><strong><span class="en">Press and speak</span><span class="bn">চেপে বলুন</span></strong><span><span class="en">Win + Left Ctrl for Bangla, Win + Left Shift for English.</span><span class="bn">বাংলার জন্য Win + Left Ctrl, ইংরেজির জন্য Win + Left Shift।</span></span></li>
    <li><strong><span class="en">Pause</span><span class="bn">থামুন</span></strong><span><span class="en">SHUNCHi sends your recording to Gemini for transcription.</span><span class="bn">SHUNCHi আপনার রেকর্ডিং লেখায় রূপান্তরের জন্য Gemini-তে পাঠায়।</span></span></li>
    <li><strong><span class="en">The text appears</span><span class="bn">লেখা বসে যায়</span></strong><span><span class="en">The polished text is typed at your cursor.</span><span class="bn">গোছানো লেখা কার্সরের জায়গায় বসে যায়।</span></span></li>
  </ol>
</div></section>

<section id="setup" class="alt"><div class="wrap setup">
  <div class="head"><div class="eyebrow"><span class="en">Setup guide</span><span class="bn">সেটআপ গাইড</span></div>
    <h2><span class="en">Ready in about 1.5 minutes</span><span class="bn">প্রায় ১.৫ মিনিটেই তৈরি</span></h2>
    <p><span class="en">You need Windows 10 or 11 (64-bit), a microphone and an internet connection. Most laptops have a microphone built in. A desktop computer needs a separate microphone or headset.</span><span class="bn">লাগবে উইন্ডোজ ১০ বা ১১ (৬৪-বিট), একটি মাইক্রোফোন আর ইন্টারনেট সংযোগ। ল্যাপটপে মাইক্রোফোন বিল্ট-ইন থাকে। ডেস্কটপ কম্পিউটারে আলাদা মাইক্রোফোন বা হেডসেট লাগবে।</span></p></div>
  <ol class="steps">
    <li><h3><span class="en">Get a free Gemini API key</span><span class="bn">ফ্রি Gemini API কী নিন</span></h3>
      <div class="en"><p>The key lets SHUNCHi use Google's speech recognition on your own free quota.</p><ul><li>Open <a href="https://aistudio.google.com/apikey" rel="noopener">aistudio.google.com/apikey</a> and sign in with a Google account.</li><li>Choose <b>Create API key</b> and copy it.</li></ul></div>
      <div class="bn"><p>এই কী দিয়ে SHUNCHi আপনার নিজের ফ্রি কোটায় গুগলের স্পিচ রিকগনিশন ব্যবহার করে।</p><ul><li><a href="https://aistudio.google.com/apikey" rel="noopener">aistudio.google.com/apikey</a> খুলে গুগল অ্যাকাউন্টে সাইন ইন করুন।</li><li><b>Create API key</b> চেপে কী-টি কপি করুন।</li></ul></div></li>
    <li><h3><span class="en">Download and install</span><span class="bn">ডাউনলোড ও ইনস্টল করুন</span></h3>
      <div class="en"><p>Download the installer and run it. No administrator rights are needed.</p><ul><li>The desktop shortcut and “start with Windows” options are already ticked. Untick what you do not want.</li><li>When installation finishes, SHUNCHi opens by itself.</li></ul></div>
      <div class="bn"><p>ইনস্টলার ডাউনলোড করে চালান। অ্যাডমিন অনুমতি লাগে না।</p><ul><li>ডেস্কটপ শর্টকাট আর “উইন্ডোজের সাথে চালু” অপশন দুটি আগে থেকেই টিক দেওয়া থাকে। যেটা চান না সেটা বাদ দিন।</li><li>ইনস্টল শেষ হলেই SHUNCHi নিজে থেকে খুলে যাবে।</li></ul></div>
      <a class="btn btn-primary" href="download/index.html"><span class="en">Go to download</span><span class="bn">ডাউনলোড পাতায় যান</span></a>
      <div class="note"><b>SmartScreen</b><span><span class="en">If Windows shows “Windows protected your PC”, choose <b>More info</b>, then <b>Run anyway</b>. The installer is new and not yet widely downloaded.</span><span class="bn">উইন্ডোজ “Windows protected your PC” দেখালে <b>More info</b> চেপে <b>Run anyway</b> দিন। ইনস্টলারটি নতুন বলে এমন দেখায়।</span></span></div></li>
    <li><h3><span class="en">Paste your key in Settings</span><span class="bn">Settings-এ কী বসান</span></h3>
      <div class="en"><ul><li>In the SHUNCHi window, open <b>Settings</b>.</li><li>Paste the key into the Gemini API key box and choose <b>Save &amp; test</b>.</li><li>A green <b>Connected</b> label means you are ready.</li></ul></div>
      <div class="bn"><ul><li>SHUNCHi-র উইন্ডোতে <b>Settings</b> খুলুন।</li><li>Gemini API key বক্সে কী পেস্ট করে <b>Save &amp; test</b> চাপুন।</li><li>সবুজ রঙে <b>Connected</b> দেখালে আপনি তৈরি।</li></ul></div></li>
    <li><h3><span class="en">Try it</span><span class="bn">চালিয়ে দেখুন</span></h3>
      <div class="en"><ul><li>Click where you want to type: a browser, WhatsApp, Word, Notepad.</li><li>Press <kbd>Win</kbd> + <kbd>Left Ctrl</kbd> for Bangla or <kbd>Win</kbd> + <kbd>Left Shift</kbd> for English, and speak.</li><li>Stop talking. The popup shows “Writing” and the text appears at your cursor.</li><li>Press the same shortcut again to finish early.</li></ul></div>
      <div class="bn"><ul><li>যেখানে লিখতে চান সেখানে ক্লিক করুন: ব্রাউজার, হোয়াটসঅ্যাপ, ওয়ার্ড বা নোটপ্যাড।</li><li>বাংলার জন্য <kbd>Win</kbd> + <kbd>Left Ctrl</kbd>, ইংরেজির জন্য <kbd>Win</kbd> + <kbd>Left Shift</kbd> চেপে কথা বলুন।</li><li>থামলেই পপআপে “Writing” দেখাবে এবং লেখা কার্সরের জায়গায় বসে যাবে।</li><li>আগে শেষ করতে চাইলে একই শর্টকাট আবার চাপুন।</li></ul></div></li>
    <li><h3><span class="en">Tune it (optional)</span><span class="bn">নিজের মতো সাজান (ঐচ্ছিক)</span></h3>
      <div class="en"><ul><li><b>Finish after a pause:</b> Quick, Normal or Relaxed. Choose Relaxed if you speak slowly.</li><li><b>Microphone:</b> pick another input if the default is wrong.</li><li><b>Start with Windows:</b> on by default. Closing the window keeps SHUNCHi running in the system tray. Use Exit in the tray menu to quit.</li></ul></div>
      <div class="bn"><ul><li><b>Finish after a pause:</b> Quick, Normal বা Relaxed। ধীরে কথা বললে Relaxed বেছে নিন।</li><li><b>Microphone:</b> ডিফল্ট মাইক ঠিক না হলে অন্যটি বেছে নিন।</li><li><b>Start with Windows:</b> ডিফল্টে চালু। উইন্ডো বন্ধ করলে SHUNCHi সিস্টেম ট্রেতে চলতে থাকে। পুরোপুরি বন্ধ করতে ট্রে মেনুর Exit চাপুন।</li></ul></div></li>
  </ol>
</div>
{videos_block("", 3)}</section>

<section id="apps"><div class="wrap">
  <div class="head"><div class="eyebrow"><span class="en">More Apps</span><span class="bn">আরও অ্যাপ</span></div>
    <h2><span class="en">More from the developer</span><span class="bn">ডেভেলপারের আরও কাজ</span></h2>
    <p><span class="en">Free apps and everyday tools, added one by one. Everything is in one place.</span><span class="bn">ফ্রি অ্যাপ ও দৈনন্দিন কাজের টুল, একে একে যোগ হচ্ছে। সবকিছু এক জায়গায়।</span></p></div>
  <div class="app-list" id="app-list">''' + apps_static("", 4) + f'''</div>
  <h3 style="margin:44px 0 18px;font-size:22px"><span class="en">Most powerful free tools, coming soon</span><span class="bn">সবচেয়ে কাজের ফ্রি টুল, শীঘ্রই আসছে</span></h3>
  <div id="tool-grid">''' + tools_static(HOME_TOOLS) + f'''</div>
  <p style="margin-top:28px"><a class="btn btn-ghost" href="apps/index.html"><span class="en">See all apps and tools</span><span class="bn">সব অ্যাপ ও টুল দেখুন</span> <span aria-hidden="true">→</span></a></p>
  ''' + SUGGEST_FORM + f'''
</div></section>

<section id="blog"><div class="wrap">
  <div class="head"><div class="eyebrow"><span class="en">Blog</span><span class="bn">ব্লগ</span></div>
    <h2><span class="en">Guides and tips</span><span class="bn">গাইড ও টিপস</span></h2>
    <p><span class="en">Learn Bangla voice typing, set up your free key and get more done.</span><span class="bn">বাংলা ভয়েস টাইপিং শিখুন, ফ্রি কী সেট করুন ও কাজ দ্রুত করুন।</span></p></div>
  <div class="post-grid">{"".join(post_card(p, "") for p in POSTS[:3])}</div>
  <p style="margin-top:28px"><a class="btn btn-ghost" href="blog/index.html"><span class="en">All articles</span><span class="bn">সব লেখা</span> <span aria-hidden="true">→</span></a></p>
</div></section>

<section id="faq" class="alt"><div class="wrap">
  <div class="head"><div class="eyebrow"><span class="en">FAQ</span><span class="bn">প্রশ্নোত্তর</span></div>
    <h2><span class="en">Questions and fixes</span><span class="bn">প্রশ্ন ও সমাধান</span></h2></div>
  <div class="faq">{faq}</div>
</div></section>

<section id="developer"><div class="wrap dev">
  <img src="assets/developer-ruhul.jpg" alt="Ruhul Amin" width="200" height="200" loading="lazy">
  <div>
    <div class="eyebrow"><span class="en">Creator and developer</span><span class="bn">নির্মাতা ও ডেভেলপার</span></div>
    <h2>Ruhul Amin</h2>
    <p class="role"><span class="en">Builder of SHUNCHi · Bangladesh</span><span class="bn">SHUNCHi-র নির্মাতা · বাংলাদেশ</span></p>
    <div class="story">
      <div class="en">
        <p><strong>SHUNCHi began with one question: why should voice typing in Bangla not be easy, fast and free for everyone?</strong></p>
        <p>How much more typing do we have to learn? Why should anyone pay just to work in their own language? Why should learning small digital tasks mean running to a training centre?</p>
        <p>Technology is here to make our work easier, not harder.</p>
        <p>That thought is where SHUNCHi started. Our goal is to build simple, useful tools that everyone can use in their own language: easily, comfortably and at almost no cost.</p>
        <p>Starting with voice typing, many everyday tools will be added to SHUNCHi one by one, such as email, CV making and file conversion.</p>
        <p class="tag">SHUNCHi: let technology be easy, for everyone.</p>
      </div>
      <div class="bn">
        <p><strong>SHUNCHi-র যাত্রা শুরু হয়েছিল একটি প্রশ্ন থেকে—বাংলায় ভয়েস টাইপিং কেন সহজ, দ্রুত এবং সবার জন্য বিনামূল্যে হবে না?</strong></p>
        <p>আর কত টাইপিং শিখতে হবে? কেন নিজের ভাষায় কাজ করার জন্য টাকা খরচ করতে হবে? কেন ছোট ছোট ডিজিটাল কাজ শেখার জন্য ট্রেনিং সেন্টারে দৌড়াতে হবে?</p>
        <p>প্রযুক্তি তো আমাদের কাজ সহজ করার জন্য, কঠিন করার জন্য নয়!</p>
        <p>সেই ভাবনা থেকেই SHUNCHi-র শুরু। আমাদের লক্ষ্য, এমন সব সহজ ও কার্যকর টুল তৈরি করা, যা সবাই নিজের ভাষায় ব্যবহার করতে পারবেন—সহজে, স্বাচ্ছন্দ্যে এবং নামমাত্র খরচে।</p>
        <p>ভয়েস টাইপিং থেকে শুরু করে ইমেইল, CV তৈরি, ফাইল কনভার্টসহ প্রতিদিনের প্রয়োজনীয় অনেক টুল একে একে যুক্ত হবে SHUNCHi-তে।</p>
        <p class="tag">SHUNCHi—প্রযুক্তি হোক সহজ, সবার জন্য।</p>
      </div>
    </div>
    <div class="links-row">
      <a class="pill" href="https://www.facebook.com/iamruhulaamin" rel="noopener">{SOCIAL_ICONS["fb"]}Facebook</a>
      <a class="pill" href="https://www.instagram.com/iamruhulaamin/" rel="noopener">{SOCIAL_ICONS["ig"]}Instagram</a>
      <a class="pill" href="https://www.linkedin.com/search/results/people/?keywords=iamruhulaamin" rel="noopener">{SOCIAL_ICONS["in"]}LinkedIn</a>
    </div>
    <div class="official">
      <div class="official-title"><span class="en">Official SHUNCHi pages</span><span class="bn">অফিসিয়াল SHUNCHi পেজ</span></div>
      <div class="official-links">
        <a href="https://www.facebook.com/voice.shunchi" rel="noopener">{SOCIAL_ICONS["fb"]}<span>Facebook</span></a>
        <a href="https://www.instagram.com/voice.shunchi/" rel="noopener">{SOCIAL_ICONS["ig"]}<span>Instagram</span></a>
        <a href="mailto:voice.shunchi@gmail.com">{SOCIAL_ICONS["mail"]}<span>voice.shunchi@gmail.com</span></a>
      </div>
    </div>
  </div>
</div></section>
</main>
''' + footer("") + '''<script src="assets/catalog.js?v=20" data-base=""></script>
<script src="assets/site.js?v=20"></script>
<script>
(function () {
  function drawApps() { renderApps(document.getElementById("app-list"), 4); }
  drawApps();
  renderTools(document.getElementById("tool-grid"), { featured: ["build-cv","invoice-maker","pdf-tools","image-compressor","budget-calculator","tour-calculator","bangla-typing","qr-code","bijoy-unicode"] });
  loadRemoteApps(drawApps);
})();
</script>
</body>
</html>
'''
write("index.html", home)

# ====================================================================== APPS HUB
reg("apps/", "0.8", "weekly")
hub = head("../", "Free Tools and Apps: CV Maker, Invoice, Budget and More | SHUNCHi",
           "Free apps and tools from the maker of SHUNCHi: CV and invoice makers, budget and tour calculators, Bangla text tools. Free, no sign-up.",
           "apps/", ld=[crumbs_ld([("Home", ""), ("More Apps", "apps/")]), {"@context": "https://schema.org", "@type": "CollectionPage", "name": "SHUNCHi apps and free tools", "url": DOMAIN + "/apps/",
             "mainEntity": {"@type": "ItemList", "itemListElement": [{"@type": "ListItem", "position": i + 1, "name": t["t"], "description": t["d"]} for i, t in enumerate(TOOLS)]}}]) + header("../", "apps") + '''
<main id="main">
<div class="wrap page-head">
  <ol class="crumbs"><li><a href="../index.html"><span class="en">Home</span><span class="bn">হোম</span></a></li><li aria-current="page"><span class="en">More Apps</span><span class="bn">আরও অ্যাপ</span></li></ol>
  <h1><span class="en">More Apps</span><span class="bn">আরও অ্যাপ</span></h1>
  <p><span class="en">Software and free everyday tools from the maker of SHUNCHi, all in one place. Private, free and without sign-up. New tools go live as soon as they are ready.</span><span class="bn">SHUNCHi-র নির্মাতার সফটওয়্যার ও দৈনন্দিন কাজের ফ্রি টুল, সবকিছু এক জায়গায়। প্রাইভেট, ফ্রি এবং সাইন আপ ছাড়া। নতুন টুল তৈরি হওয়ামাত্র চালু হবে।</span></p>
  <div class="stats" id="stats" aria-live="polite"></div>
</div>

<section style="padding-top:36px"><div class="wrap">
  <div class="head" style="margin-bottom:22px"><h2 style="font-size:28px"><span class="en">Apps</span><span class="bn">অ্যাপ</span></h2></div>
  <div class="app-list" id="app-list">''' + apps_static("../") + '''</div>
</div></section>

<section class="alt" style="padding-top:44px"><div class="wrap">
  <div class="head" style="margin-bottom:22px"><h2 style="font-size:28px"><span class="en">Free tools</span><span class="bn">ফ্রি টুল</span></h2>
    <p><span class="en">Search, or pick a category. “Next up” tools are being built now.</span><span class="bn">খুঁজুন, অথবা একটি ক্যাটাগরি বেছে নিন। “পরবর্তী” চিহ্নিত টুলগুলো এখন তৈরি হচ্ছে।</span></p></div>
  <div class="toolbar">
    <label class="sr" for="search" style="position:absolute;left:-999px"><span class="en">Search tools</span><span class="bn">টুল খুঁজুন</span></label>
    <input class="search" id="search" type="search" inputmode="search" autocomplete="off" placeholder="Search tools / টুল খুঁজুন">
    <div class="chips" id="chips" role="group" aria-label="Categories"></div>
  </div>
  <div id="results">''' + tools_static(None, True) + '''</div>
  <div class="suggest"><div><h3><span class="en">Need a tool that is not here?</span><span class="bn">যে টুলটি দরকার সেটি নেই?</span></h3>
    <p><span class="en">Tell us what would save you time. The most requested tools are built first.</span><span class="bn">কোন টুল আপনার সময় বাঁচাবে জানান। সবচেয়ে বেশি চাওয়া টুলগুলো আগে বানানো হবে।</span></p></div>
    <a class="btn btn-primary" href="https://www.facebook.com/voice.shunchi" rel="noopener"><span class="en">Suggest a tool</span><span class="bn">টুলের পরামর্শ দিন</span></a></div>
</div></section>
<section><div class="wrap">''' + SUGGEST_FORM + '''</div></section>
</main>
''' + footer("../") + '''<script src="../assets/catalog.js?v=20" data-base="../"></script>
<script src="../assets/site.js?v=20"></script>
<script>
(function () {
  var state = { cat: "all", q: "" }, results = document.getElementById("results");
  function draw() { renderTools(results, { cat: state.cat, q: state.q, grouped: true }); }
  function apps() { renderApps(document.getElementById("app-list")); }
  var c = SITE_COUNTS();
  document.getElementById("stats").innerHTML =
    '<div><b>' + c.tools + '</b><span><span class="en">free tools planned</span><span class="bn">ফ্রি টুল পরিকল্পনায়</span></span></div>' +
    '<div><b>' + c.cats + '</b><span><span class="en">categories</span><span class="bn">ক্যাটাগরি</span></span></div>' +
    '<div><b>0৳</b><span><span class="en">always free</span><span class="bn">সবসময় ফ্রি</span></span></div>';
  renderCategoryTabs(document.getElementById("chips"), function (k) { state.cat = k; draw(); });
  document.getElementById("search").addEventListener("input", function () { state.q = this.value; draw(); });
  apps(); draw(); loadRemoteApps(apps);
})();
</script>
</body>
</html>
'''
write("apps/index.html", hub)

# ====================================================================== TOOL TEMPLATE
tmpl = head("../", "Tool name | SHUNCHi", "One sentence about the tool.", "apps/tool-name.html", robots="noindex,follow") + header("../", "apps") + '''
<!--
  TEMPLATE FOR A NEW TOOL PAGE
  1. Copy this file to apps/<id>.html. Use the same <id> as the tool in assets/catalog.js.
  2. Replace the title, the heading, the description and the content of the card.
  3. In assets/catalog.js change that tool's  s: "soon"  to  s: "live".  The card opens this page automatically.
  Write both languages with <span class="en">..</span><span class="bn">..</span>. Keep the tool inside the browser; do not upload user data.
-->
<main id="main">
<div class="wrap page-head">
  <ol class="crumbs"><li><a href="../index.html"><span class="en">Home</span><span class="bn">হোম</span></a></li><li><a href="index.html"><span class="en">More Apps</span><span class="bn">আরও অ্যাপ</span></a></li><li aria-current="page"><span class="en">Tool name</span><span class="bn">টুলের নাম</span></li></ol>
  <h1><span class="en">Tool name</span><span class="bn">টুলের নাম</span></h1>
  <p><span class="en">One sentence about what this tool does.</span><span class="bn">টুলটি কী করে তার এক লাইন।</span></p>
</div>
<section style="padding-top:28px"><div class="wrap">
  <div class="dl-card" id="tool-area"><p><span class="en">Build the tool here.</span><span class="bn">টুলটি এখানে বানান।</span></p></div>
</div></section>
</main>
''' + footer("../") + '''<script src="../assets/site.js?v=20"></script>
</body>
</html>
'''
write("apps/_template.html", tmpl)

# ====================================================================== DOWNLOAD
reg("download/", "0.9", "weekly")
dl = head("../", "Download SHUNCHi for Windows 10 and 11: Free Bangla Voice Typing", "Download SHUNCHi, the free AI voice typing app for Windows 10 and 11 (64-bit). Type Bangla and English by voice in any app. | SHUNCHi ডাউনলোড।", "download/",
          ld=[crumbs_ld([("Home", ""), ("Download", "download/")])]) + header("../") + '''
<main id="main">
<div class="wrap page-head dl">
  <ol class="crumbs"><li><a href="../index.html"><span class="en">Home</span><span class="bn">হোম</span></a></li><li aria-current="page"><span class="en">Download</span><span class="bn">ডাউনলোড</span></li></ol>
  <h1><span class="en">Download SHUNCHi</span><span class="bn">SHUNCHi ডাউনলোড করুন</span></h1>
  <p><span class="en">Free AI voice typing for Windows 10 and 11 (64-bit).</span><span class="bn">উইন্ডোজ ১০ ও ১১ (৬৪-বিট)-এর জন্য ফ্রি এআই ভয়েস টাইপিং।</span></p>
  <div class="dl-card">
    <div class="dl-top"><h2>SHUNCHi <span id="v">''' + html.escape(LATEST_VER) + '''</span></h2><span class="dl-date" id="date"></span></div>
    <div class="dl-actions">
      <a class="btn btn-primary dl-main" id="get" href="#" hidden><span class="en">Download for Windows</span><span class="bn">উইন্ডোজের জন্য ডাউনলোড করুন</span></a>
      <p class="dl-sub" id="full" hidden><span class="en">Prefer the full offline installer?</span><span class="bn">পুরো অফলাইন ইনস্টলার চান?</span> <a id="full-link" href="#"><span class="en">Download it here</span><span class="bn">এখান থেকে নামান</span></a> <span id="size"></span></p>
    </div>
    <p class="dl-sub" id="soon"><span class="en">The installer will appear here as soon as the first release is published.</span><span class="bn">প্রথম রিলিজ প্রকাশ হলেই ইনস্টলার এখানে পাওয়া যাবে।</span></p>
    <p class="dl-sub" id="started" hidden><span class="en">Your download should start in a moment. If it does not, use the button.</span><span class="bn">কিছুক্ষণের মধ্যে ডাউনলোড শুরু হবে। না হলে বাটনটি চাপুন।</span></p>
    <div class="dl-need"><b><span class="en">What you need</span><span class="bn">যা লাগবে</span></b>
      <ul><li><span class="en">Windows 10 or 11 (64-bit)</span><span class="bn">উইন্ডোজ ১০ বা ১১ (৬৪-বিট)</span></li>
      <li><span class="en">A microphone: built into most laptops, a desktop needs a separate mic or headset</span><span class="bn">মাইক্রোফোন: ল্যাপটপে বিল্ট-ইন থাকে, ডেস্কটপে আলাদা মাইক বা হেডসেট লাগবে</span></li>
      <li><span class="en">Internet and a free Gemini API key</span><span class="bn">ইন্টারনেট ও একটি ফ্রি Gemini API কী</span></li></ul></div>
    <details class="dl-notes" id="notes-box" hidden open><summary><span class="en">What is new in this version</span><span class="bn">এই ভার্সনে নতুন কী</span></summary>
      <ul class="en" id="notes-en"></ul><ul class="bn" id="notes-bn"></ul></details>
  </div>
  <div class="dl-help">
    <h2 style="font-size:22px;margin-bottom:12px"><span class="en">After downloading</span><span class="bn">ডাউনলোডের পর</span></h2>
    <ol class="steps" style="margin-left:17px">
      <li><p><span class="en">Open the file. If Windows shows “Windows protected your PC”, choose <b>More info</b>, then <b>Run anyway</b>.</span><span class="bn">ফাইলটি খুলুন। উইন্ডোজ “Windows protected your PC” দেখালে <b>More info</b> চেপে <b>Run anyway</b> দিন।</span></p></li>
      <li><p><span class="en">Keep the two recommended options ticked and install. SHUNCHi opens by itself.</span><span class="bn">সুপারিশ করা দুটি অপশন টিক দেওয়া রেখে ইনস্টল করুন। SHUNCHi নিজে থেকে খুলবে।</span></p></li>
      <li><p><span class="en">Paste your free Gemini API key in Settings. <a href="../index.html#setup">See the full setup guide</a>.</span><span class="bn">Settings-এ আপনার ফ্রি Gemini API কী বসান। <a href="../index.html#setup">পুরো সেটআপ গাইড দেখুন</a>।</span></p></li>
    </ol>
  </div>
</div>
</main>
''' + footer("../") + '''<script src="../assets/site.js?v=20"></script>
<script>
(function () {
  if (!window.fetch) return;
  fetch("../update.json", { cache: "no-cache" }).then(function (r) { return r.ok ? r.json() : null; }).then(function (m) {
    if (!m) return;
    if (m.latest_version) document.getElementById("v").textContent = m.latest_version;
    function fill(id, t) { var ul = document.getElementById(id); (t || "").split("\\n").forEach(function (l) { l = l.replace(/^\\s*[-*•]\\s*/, "").trim(); if (l) { var li = document.createElement("li"); li.textContent = l; ul.appendChild(li); } }); return ul.children.length > 0; }
    var en = fill("notes-en", m.release_notes_en || m.release_notes), bnn = fill("notes-bn", m.release_notes_bn || m.release_notes_en || m.release_notes);
    if (en || bnn) document.getElementById("notes-box").hidden = false;
    if (m.released) { try { var d = new Date(m.released + "T00:00:00"); document.getElementById("date").textContent = d.toLocaleDateString(document.documentElement.lang === "bn" ? "bn-BD" : "en-GB", { day: "numeric", month: "long", year: "numeric" }); } catch (e) { document.getElementById("date").textContent = m.released; } }
    var web = /^https:\\/\\//.test(m.web_installer_url || "") ? m.web_installer_url : "";
    var fullUrl = /^https:\\/\\//.test(m.installer_url || "") ? m.installer_url : "";
    var main = web || fullUrl;
    if (main) {
      var get = document.getElementById("get"); get.href = main; get.hidden = false;
      document.getElementById("soon").hidden = true;
      if (web && fullUrl) {
        document.getElementById("full-link").href = fullUrl; document.getElementById("full").hidden = false;
        if (m.installer_size) document.getElementById("size").textContent = "(" + Math.round(m.installer_size / 1048576) + " MB)";
      }
      if (location.hash === "#start") {
        document.getElementById("started").hidden = false;
        setTimeout(function () { location.href = main; }, 1200);
      }
    }
  }).catch(function () {});
})();
</script>
</body>
</html>
'''
write("download/index.html", dl)

# ====================================================================== PRIVACY
reg("privacy.html", "0.3", "yearly")
priv = head("", "Privacy Policy | SHUNCHi", "How SHUNCHi handles your voice, text and API key. Your key stays on your PC and audio goes only to Google for transcription.", "privacy.html",
            ld=[crumbs_ld([("Home", ""), ("Privacy", "privacy.html")])]) + header("") + '''
<main id="main">
<div class="wrap page-head">
  <ol class="crumbs"><li><a href="index.html"><span class="en">Home</span><span class="bn">হোম</span></a></li><li aria-current="page"><span class="en">Privacy</span><span class="bn">গোপনীয়তা</span></li></ol>
  <h1><span class="en">Privacy</span><span class="bn">গোপনীয়তা</span></h1>
  <p><span class="en">Short and plain. What SHUNCHi does with your voice, your text and your key.</span><span class="bn">সংক্ষেপে ও সহজ ভাষায়: আপনার কণ্ঠ, লেখা ও কী নিয়ে SHUNCHi কী করে।</span></p>
</div>
<section style="padding-top:20px"><div class="wrap prose">
  <div class="en">
    <h2>Your voice</h2><p>When you dictate, SHUNCHi records from your microphone only between the start and the end of that dictation. The recording is sent to Google's Gemini service to be turned into text, using your own API key. We do not receive it and we do not run a server that stores it.</p>
    <h2>Google's free tier</h2><p>On Google's free tier, content you send may be used by Google to improve its products. Please do not dictate passwords, bank details or other secrets. Paid Gemini plans have different terms.</p>
    <h2>Your API key</h2><p>Your key is stored in Windows Credential Manager on your computer. It is sent only to Google when you dictate or press “Save &amp; test”. It never goes to this website.</p>
    <h2>Your history</h2><p>The list of past dictations is kept on your computer only. You can clear it from the Voice History page.</p>
    <h2>This website and updates</h2><p>The app checks <code>shunchiai.com/update.json</code> to learn whether a new version exists. That request contains the app version in its user agent and nothing about you. The website does not use advertising trackers.</p>
    <h2>Contact</h2><p>Questions: <a href="mailto:voice.shunchi@gmail.com">voice.shunchi@gmail.com</a></p>
  </div>
  <div class="bn">
    <h2>আপনার কণ্ঠ</h2><p>আপনি যখন ডিকটেট করেন, শুধু তখনই, শুরু থেকে শেষ পর্যন্ত, SHUNCHi আপনার মাইক্রোফোন থেকে রেকর্ড করে। রেকর্ডিংটি আপনার নিজের API কী দিয়ে লেখায় রূপান্তরের জন্য গুগলের Gemini সেবায় পাঠানো হয়। এটি আমরা পাই না এবং জমা রাখার মতো কোনো সার্ভারও আমাদের নেই।</p>
    <h2>গুগলের ফ্রি টিয়ার</h2><p>গুগলের ফ্রি টিয়ারে আপনার পাঠানো কনটেন্ট গুগল তাদের পণ্যের উন্নয়নে ব্যবহার করতে পারে। তাই পাসওয়ার্ড, ব্যাংকের তথ্য বা অন্য গোপন কিছু ডিকটেট করবেন না। পেইড Gemini প্ল্যানের শর্ত আলাদা।</p>
    <h2>আপনার API কী</h2><p>কী-টি আপনার কম্পিউটারের Windows Credential Manager-এ থাকে। ডিকটেশনের সময় বা “Save &amp; test” চাপলে এটি শুধু গুগলে যায়। এই ওয়েবসাইটে কখনও আসে না।</p>
    <h2>আপনার হিস্ট্রি</h2><p>আগের ডিকটেশনের তালিকা শুধু আপনার কম্পিউটারেই থাকে। Voice History পাতা থেকে আপনি তা মুছে ফেলতে পারেন।</p>
    <h2>এই ওয়েবসাইট ও আপডেট</h2><p>নতুন ভার্সন আছে কিনা জানতে অ্যাপটি <code>shunchiai.com/update.json</code> দেখে। এই অনুরোধে শুধু অ্যাপের ভার্সন থাকে, আপনার সম্পর্কে কিছু থাকে না। ওয়েবসাইটে বিজ্ঞাপনের ট্র্যাকার নেই।</p>
    <h2>যোগাযোগ</h2><p>প্রশ্ন থাকলে: <a href="mailto:voice.shunchi@gmail.com">voice.shunchi@gmail.com</a></p>
  </div>
</div></section>
</main>
''' + footer("") + '''<script src="assets/site.js?v=20"></script>
</body>
</html>
'''
if GTM_ID:
    priv = priv.replace("<h2>Contact</h2>", "<h2>Website analytics</h2><p>This website uses Google Tag Manager to count visits and see which pages help people. It does not receive your dictations, text or API key, because those never pass through this website.</p>\n    <h2>Contact</h2>", 1)
    priv = priv.replace("<h2>যোগাযোগ</h2>", "<h2>ওয়েবসাইট অ্যানালিটিক্স</h2><p>এই ওয়েবসাইট কতজন ঘুরে গেলেন ও কোন পেজ কাজে লাগছে তা জানতে Google Tag Manager ব্যবহার করে। আপনার ডিকটেশন, লেখা বা API কী এই ওয়েবসাইটের মধ্য দিয়ে যায় না, তাই এগুলো এখানে পৌঁছায় না।</p>\n    <h2>যোগাযোগ</h2>", 1)
write("privacy.html", priv)

# ====================================================================== 404
nf = head("/", "Page not found | SHUNCHi", "This page does not exist.", "404.html", robots="noindex,follow").replace('href="/assets', 'href="/assets') + header("/") + '''
<main id="main"><div class="wrap page-head" style="padding-bottom:80px">
  <h1><span class="en">Page not found</span><span class="bn">পাতাটি পাওয়া যায়নি</span></h1>
  <p><span class="en">The link may be old or mistyped.</span><span class="bn">লিংকটি পুরনো বা ভুল হতে পারে।</span></p>
  <p style="margin-top:22px"><a class="btn btn-primary" href="/index.html"><span class="en">Back to home</span><span class="bn">হোমে ফিরুন</span></a></p>
</div></main>
''' + footer("/") + '<script src="/assets/site.js?v=20"></script>\n</body>\n</html>\n'
write("404.html", nf)
print("pages written")


# ====================================================================== BLOG PAGES
def crumbs_html(P, trail):
    """trail: list of (en, bn, href or None)"""
    items = []
    for en, bn, href in trail:
        lab = f'<span class="en">{esc(en)}</span><span class="bn">{esc(bn)}</span>'
        items.append(f'<li><a href="{href}">{lab}</a></li>' if href else f'<li aria-current="page">{lab}</li>')
    return '<ol class="crumbs">' + "".join(items) + "</ol>"

for p in POSTS:
    url = f"blog/{p['slug']}.html"; reg(url, "0.7", "monthly", p["updated"])
    img = f"{DOMAIN}/{p['cover']}" if p["cover"] else None
    ld = [crumbs_ld([("Home", ""), ("Blog", "blog/"), (p["title"], url)]),
          {"@context": "https://schema.org", "@type": "BlogPosting", "headline": p["title"], "description": p["desc"], "inLanguage": p["lang"],
           "datePublished": p["date"], "dateModified": p["updated"], "mainEntityOfPage": f"{DOMAIN}/{url}",
           "image": img or f"{DOMAIN}/assets/og-cover.jpg", "keywords": ", ".join(p["tags"]),
           "author": {"@type": "Person", "name": "Ruhul Amin", "url": DOMAIN + "/#developer"},
           "publisher": {"@type": "Organization", "name": "SHUNCHi", "logo": {"@type": "ImageObject", "url": DOMAIN + "/assets/icon-512.png"}}}]
    related = [q2 for q2 in POSTS if q2["slug"] != p["slug"]][:3]
    mins = f"{p['mins']} মিনিট পড়া".translate(BN_DIGITS) if p["lang"] == "bn" else f"{p['mins']} min read"
    tags = "".join(f'<span class="tag">{esc(t)}</span>' for t in p["tags"])
    cover = f'<img class="post-cover" src="../{p["cover"]}" alt="" width="1200" height="630">' if p["cover"] else ""
    page = head("../", p["title"] + " | SHUNCHi", p["desc"], url, og_type="article", img=img, ld=ld) + header("../", "blog") + f'''
<main id="main">
<div class="wrap page-head post-head">
  {crumbs_html("../", [("Home","হোম","../index.html"),("Blog","ব্লগ","index.html"),(p["title"],p["title"],None)])}
  <div class="post-meta"><span class="tag lang-{p["lang"]}">{"বাংলা" if p["lang"]=="bn" else "English"}</span><time datetime="{p["date"]}">{nice_date(p["date"], p["lang"])}</time><span>{mins}</span></div>
  <h1 lang="{p["lang"]}">{esc(p["title"])}</h1>
  <p class="post-lead" lang="{p["lang"]}">{esc(p["desc"])}</p>
</div>
<article class="wrap post" lang="{p["lang"]}">
  {cover}
  <div class="post-body">{p["html"]}</div>
  <div class="post-tags">{tags}</div>
  <div class="post-cta"><div><h3><span class="en">Try SHUNCHi, free</span><span class="bn">SHUNCHi ফ্রিতে ব্যবহার করুন</span></h3>
    <p><span class="en">Voice typing in Bangla and English for Windows. Speak, and the text appears in any app.</span><span class="bn">উইন্ডোজে বাংলা ও ইংরেজি ভয়েস টাইপিং। বলুন, যেকোনো অ্যাপে লেখা বসে যাবে।</span></p></div>
    <a class="btn btn-primary" href="../download/index.html"><span class="en">Download for Windows</span><span class="bn">উইন্ডোজের জন্য ডাউনলোড</span></a></div>
</article>
{('<section class="alt"><div class="wrap"><div class="head" style="margin-bottom:24px"><h2 style="font-size:26px"><span class="en">More articles</span><span class="bn">আরও লেখা</span></h2></div><div class="post-grid">' + "".join(post_card(r, "../") for r in related) + "</div></div></section>") if related else ""}
</main>
''' + footer("../") + '<script src="../assets/site.js?v=20"></script>\n</body>\n</html>\n'
    write(url, page)

reg("blog/", "0.8", "weekly", POSTS[0]["date"] if POSTS else TODAY)
blog_ld = [crumbs_ld([("Home", ""), ("Blog", "blog/")]),
           {"@context": "https://schema.org", "@type": "Blog", "name": "SHUNCHi Blog", "url": DOMAIN + "/blog/", "inLanguage": ["en", "bn"],
            "blogPost": [{"@type": "BlogPosting", "headline": p["title"], "url": f"{DOMAIN}/blog/{p['slug']}.html", "datePublished": p["date"]} for p in POSTS]}]
blog_index = head("../", "Blog: Bangla Voice Typing Guides and Tips | SHUNCHi",
                  "Guides on Bangla and English voice typing for Windows, setting up your free Gemini key, and working faster. বাংলা ভয়েস টাইপিং গাইড।", "blog/", ld=blog_ld) + header("../", "blog") + f'''
<main id="main">
<div class="wrap page-head">
  {crumbs_html("../", [("Home","হোম","../index.html"),("Blog","ব্লগ",None)])}
  <h1><span class="en">Blog</span><span class="bn">ব্লগ</span></h1>
  <p><span class="en">Guides and tips on Bangla and English voice typing, setting up SHUNCHi and working faster.</span><span class="bn">বাংলা ও ইংরেজি ভয়েস টাইপিং, SHUNCHi সেটআপ এবং দ্রুত কাজ করার গাইড ও টিপস।</span></p>
</div>
<section style="padding-top:28px"><div class="wrap">
  {('<div class="post-grid">' + "".join(post_card(p, "../") for p in POSTS) + "</div>") if POSTS else '<p class="meta"><span class="en">The first articles are coming soon.</span><span class="bn">প্রথম লেখাগুলো শীঘ্রই আসছে।</span></p>'}
</div></section>
</main>
''' + footer("../") + '<script src="../assets/site.js?v=20"></script>\n</body>\n</html>\n'
write("blog/index.html", blog_index)


# ====================================================================== VIDEOS PAGE
if VIDEOS_JSON:
    reg("videos/", "0.6", "weekly")
    vld = [crumbs_ld([("Home", ""), ("Videos", "videos/")]),
           {"@context": "https://schema.org", "@type": "ItemList", "itemListElement": [
               {"@type": "ListItem", "position": i + 1, "item": {"@type": "VideoObject", "name": v.get("title_en") or v.get("title_bn"), "description": (v.get("title_en") or v.get("title_bn")) + " | SHUNCHi",
                "thumbnailUrl": f"https://i.ytimg.com/vi/{v['id']}/hqdefault.jpg", "uploadDate": v.get("date") or TODAY, "embedUrl": f"https://www.youtube.com/embed/{v['id']}", "contentUrl": f"https://www.youtube.com/watch?v={v['id']}"}}
               for i, v in enumerate(VIDEOS_JSON)]}]
    vpage = head("../", "Video Guides: Set Up SHUNCHi Step by Step | SHUNCHi",
                 "Watch short videos on how to install SHUNCHi, get a free Gemini key and type in Bangla with your voice. ভিডিও দেখে SHUNCHi সেটআপ করুন।", "videos/", ld=vld) + header("../") + f'''
<main id="main">
<div class="wrap page-head">
  {crumbs_html("../", [("Home","হোম","../index.html"),("Videos","ভিডিও",None)])}
  <h1><span class="en">Video guides</span><span class="bn">ভিডিও গাইড</span></h1>
  <p><span class="en">Short videos to help you set up and use SHUNCHi.</span><span class="bn">SHUNCHi সেটআপ ও ব্যবহারের ছোট ভিডিও।</span></p>
</div>
<section style="padding-top:28px"><div class="wrap"><div class="vids all">{"".join(video_card(v) for v in VIDEOS_JSON)}</div></div></section>
</main>
''' + footer("../") + '<script src="../assets/site.js?v=20"></script>\n</body>\n</html>\n'
    write("videos/index.html", vpage)

# RSS feed
def rss_item(p):
    return (f"<item><title>{esc(p['title'])}</title><link>{DOMAIN}/blog/{p['slug']}.html</link><guid isPermaLink=\"true\">{DOMAIN}/blog/{p['slug']}.html</guid>"
            f"<pubDate>{datetime.datetime.fromisoformat(p['date']).strftime('%a, %d %b %Y 06:00:00 +0000')}</pubDate><description>{esc(p['desc'])}</description></item>")
write("feed.xml", '<?xml version="1.0" encoding="UTF-8"?>\n<rss version="2.0"><channel><title>SHUNCHi Blog</title><link>' + DOMAIN + '/blog/</link>'
      '<description>Guides and tips on Bangla and English voice typing.</description><language>en</language>'
      + "".join(rss_item(p) for p in POSTS[:30]) + "</channel></rss>\n")

# ====================================================================== SOFTWARE PAGES (from site/data/apps.json, edited in the admin panel)
for a in APPS_JSON:
    if not a.get("id") or not a.get("name"): continue
    aid = re.sub(r"[^a-z0-9-]+", "-", a["id"].lower()).strip("-")
    live = a.get("status", "live") == "live"
    url = f"apps/{aid}.html"
    if live: reg(url, "0.8", "monthly", a.get("updated") or TODAY)
    te, tb = a.get("tagline_en") or a.get("tagline") or "", a.get("tagline_bn") or a.get("tagline_en") or ""
    de, db = a.get("desc_en") or te, a.get("desc_bn") or a.get("desc_en") or tb
    logo = f'<img src="../{a["logo"]}" alt="{esc(a["name"])} logo" width="96" height="96" style="border-radius:20px;margin-bottom:12px">' if a.get("logo") else ""
    ld = [crumbs_ld([("Home", ""), ("More Apps", "apps/"), (a["name"], url)]),
          {"@context": "https://schema.org", "@type": "SoftwareApplication", "name": a["name"], "description": te or de, "applicationCategory": a.get("category", "UtilitiesApplication"),
           "operatingSystem": a.get("platform", "Windows"), "softwareVersion": a.get("version", ""), "url": f"{DOMAIN}/{url}",
           "offers": {"@type": "Offer", "price": "0", "priceCurrency": "USD"}, "author": {"@type": "Person", "name": "Ruhul Amin"},
           **({"downloadUrl": a["url"]} if a.get("url", "").startswith("http") else {})}]
    dlbtn = (f'<a class="btn btn-primary" href="{esc(a["url"])}" rel="noopener"><span class="en">Download</span><span class="bn">ডাউনলোড</span></a>'
             if live and a.get("url") else '<span class="badge"><span class="en">Coming soon</span><span class="bn">শীঘ্রই আসছে</span></span>')
    page = head("../", f'{a["name"]}: {te} | SHUNCHi' if te else f'{a["name"]} | SHUNCHi', te or de, url, ld=ld, robots="index,follow,max-image-preview:large" if live else "noindex,follow") + header("../", "apps") + f'''
<main id="main">
<div class="wrap page-head dl">
  {crumbs_html("../", [("Home","হোম","../index.html"),("More Apps","আরও অ্যাপ","index.html"),(a["name"],a["name"],None)])}
  {logo}
  <h1>{esc(a["name"])} {('<span class="ver">'+esc(a["version"])+'</span>') if a.get("version") else ""}</h1>
  <p>{bi(te, tb)}</p>
  <div class="dl-card"><p class="body-text">{bi(de, db)}</p>
    <p class="meta"><b><span class="en">Platform</span><span class="bn">প্ল্যাটফর্ম</span>:</b> {esc(a.get("platform","Windows"))} &nbsp;·&nbsp; <b><span class="en">Price</span><span class="bn">মূল্য</span>:</b> <span class="en">Free</span><span class="bn">ফ্রি</span>
    {('&nbsp;·&nbsp; <b><span class="en">Updated</span><span class="bn">আপডেট</span>:</b> ' + esc(a["updated"])) if a.get("updated") else ""}</p>
    {dlbtn}</div>
</div>
</main>
''' + footer("../") + '<script src="../assets/site.js?v=20"></script>\n</body>\n</html>\n'
    write(url, page)

# ====================================================================== SITEMAP + ROBOTS
SITEMAP.sort(key=lambda r: (-float(r[2]), r[0]))
write("sitemap.xml", '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + "".join(
    f"<url><loc>{DOMAIN}/{p}</loc><lastmod>{lm}</lastmod><changefreq>{fr}</changefreq><priority>{pr}</priority></url>\n" for p, lm, pr, fr in SITEMAP) + "</urlset>\n")
write("robots.txt", f"User-agent: *\nAllow: /\nDisallow: /apps/_template.html\n\nSitemap: {DOMAIN}/sitemap.xml\n")
print("sitemap urls:", len(SITEMAP), "posts:", len(POSTS), "software pages:", len([a for a in APPS_JSON if a.get('id')]))
