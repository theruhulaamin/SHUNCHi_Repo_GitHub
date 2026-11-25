"""Writes site/stats.json (public download count) from GitHub release asset counters.
GitHub counts every asset download. The small web installer also downloads the full installer, so one install
can be counted twice. For a release that has both, the number of downloads is max(web installer, full installer)."""
import json, os, re, datetime, urllib.request
repo = os.environ.get("GITHUB_REPOSITORY", "theruhulaamin/SHUNCHi_Repo_GitHub")
req = urllib.request.Request(f"https://api.github.com/repos/{repo}/releases?per_page=100",
    headers={"Accept": "application/vnd.github+json", "User-Agent": "shunchi-stats", "Authorization": "Bearer " + os.environ.get("GH_TOKEN", "")})
rels = json.load(urllib.request.urlopen(req, timeout=60))
total = 0
for r in rels:
    if r.get("draft") or not re.match(r"^v\d", r.get("tag_name", "")): continue
    web = full = 0
    for a in r.get("assets", []):
        n = a["name"].lower()
        if not n.endswith(".exe"): continue
        if n == "shunchi_setup.exe": web += a.get("download_count", 0)
        else: full += a.get("download_count", 0)
    total += max(web, full)
json.dump({"downloads": total, "updated": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")}, open("site/stats.json", "w"))
print("downloads", total)
