"""Run by release.yml after a GitHub Release is published.
Writes site/update.json (SHUNCHi) or site/updates/<slug>.json (other apps).
Tag formats: v4.5.0  or  <slug>-v1.2.0
SHUNCHi releases must contain two .exe assets:
  SHUNCHi_Setup_<version>.exe  full installer (its SHA-256 is computed here)
  SHUNCHi_Setup.exe            small web installer, same name every release"""
import json, os, re, datetime, pathlib, hashlib, urllib.request
tag = os.environ["TAG"]; body = os.environ.get("BODY", ""); assets = os.environ.get("ASSETS", "").split()
repo = os.environ.get("GITHUB_REPOSITORY", "theruhulaamin/SHUNCHi_Repo_GitHub")
m = re.match(r"^(?:(?P<slug>[a-z0-9-]+)-)?v(?P<ver>\d+(?:\.\d+){1,3})$", tag)
if not m: raise SystemExit(f"Tag '{tag}' must look like v4.5.0 or my-app-v1.2.0")
slug, ver = m.group("slug"), m.group("ver")
name = lambda u: u.rsplit("/", 1)[-1]
exes = [a for a in assets if a.lower().endswith(".exe")]
web = next((a for a in exes if name(a).lower() == "shunchi_setup.exe"), "")
full = next((a for a in exes if a != web), "")
def clean(t): return "\n".join(l.strip() for l in t.strip().splitlines() if l.strip())[:1500]
parts = re.split(r"(?m)^\s*-{3,}\s*$", body.replace("\r", ""), maxsplit=1)
notes_en = clean(parts[0]); notes_bn = clean(parts[1]) if len(parts) > 1 else ""
notes = notes_en
site = pathlib.Path("site")
data = {"latest_version": ver, "download_url": "https://shunchiai.com/download/" if not slug else "",
        "installer_url": full, "installer_sha256": "", "installer_size": 0,
        "web_installer_url": f"https://github.com/{repo}/releases/latest/download/SHUNCHi_Setup.exe" if web else "",
        "release_notes": notes or f"Version {ver}", "release_notes_en": notes_en, "release_notes_bn": notes_bn, "released": datetime.date.today().isoformat()}
if full and not slug:
    h = hashlib.sha256(); size = 0
    req = urllib.request.Request(full, headers={"User-Agent": "shunchi-release"})
    with urllib.request.urlopen(req, timeout=300) as r:
        for chunk in iter(lambda: r.read(1 << 20), b""):
            h.update(chunk); size += len(chunk)
    data["installer_sha256"] = h.hexdigest(); data["installer_size"] = size
if web and not slug:
    try:
        n = 0
        with urllib.request.urlopen(urllib.request.Request(web, headers={"User-Agent": "shunchi-release"}), timeout=120) as r:
            for chunk in iter(lambda: r.read(1 << 20), b""): n += len(chunk)
        data["web_installer_size"] = n
    except Exception: pass
if not slug and not (full and web):
    raise SystemExit("A SHUNCHi release needs BOTH SHUNCHi_Setup_<version>.exe and SHUNCHi_Setup.exe attached.")
if slug:
    (site / "updates").mkdir(exist_ok=True)
    (site / "updates" / f"{slug}.json").write_text(json.dumps(data, indent=2, ensure_ascii=False))
else:
    data["apps"] = json.loads((site / "data" / "apps.json").read_text() or "[]")
    (site / "update.json").write_text(json.dumps(data, indent=2, ensure_ascii=False))
print("wrote", slug or "update.json", ver, full)
