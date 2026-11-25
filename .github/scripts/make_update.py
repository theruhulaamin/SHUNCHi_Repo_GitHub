"""Run by release.yml after a GitHub Release is published. Writes site/update.json (SHUNCHi)
or site/updates/<slug>.json (other apps). Tag formats: v4.5.0  or  <slug>-v1.2.0"""
import json, os, re, datetime, pathlib
tag = os.environ["TAG"]; body = os.environ.get("BODY", ""); assets = os.environ.get("ASSETS", "").split()
m = re.match(r"^(?:(?P<slug>[a-z0-9-]+)-)?v(?P<ver>\d+(?:\.\d+){1,3})$", tag)
if not m: raise SystemExit(f"Tag '{tag}' must look like v4.5.0 or my-app-v1.2.0")
slug, ver = m.group("slug"), m.group("ver")
installer = next((a for a in assets if a.lower().endswith((".exe", ".msi", ".zip"))), "")
notes = re.sub(r"\s+", " ", body).strip()[:600]
site = pathlib.Path("site")
data = {"latest_version": ver, "download_url": "https://shunchiai.com/download/" if not slug else "",
        "installer_url": installer, "release_notes": notes or f"Version {ver}",
        "released": datetime.date.today().isoformat()}
if slug:
    (site / "updates").mkdir(exist_ok=True)
    (site / "updates" / f"{slug}.json").write_text(json.dumps(data, indent=2, ensure_ascii=False))
else:
    apps = json.loads((site / "data" / "apps.json").read_text() or "[]")
    data["apps"] = apps
    (site / "update.json").write_text(json.dumps(data, indent=2, ensure_ascii=False))
print("wrote", slug or "update.json", ver, installer)
