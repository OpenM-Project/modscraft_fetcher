import html
import os
import random
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

import bs4
import cloudscraper

requests = cloudscraper.create_scraper()

if len(sys.argv) != 2:
    print(f"Error: This program needs 1 argument, got {len(sys.argv) - 1}\n")
    print(f"Usage: {sys.argv[0]} <output-html-file>\n")
    print("Parses all MCPE releases from ModsCraft and writes a static HTML site.")
    sys.exit(1)


def pathify(string):
    return re.sub(r"[^a-z0-9_.-]", "", string.replace(" ", "_").lower())


def parse_version(v):
    parts = []
    for p in v.split("."):
        if "/" in p:
            p = p.split("/")[0]
        try:
            parts.append(int(p))
        except ValueError:
            parts.append(0)
    return parts


def html_escape(text):
    return html.escape(text, quote=True)


def create_html_grid(items, cols=3):
    if not items:
        return ""

    rows = []
    for i in range(0, len(items), cols):
        chunk = items[i:i + cols]
        chunk += [""] * (cols - len(chunk))
        cells = "".join(f"<td>{item}</td>" for item in chunk)
        rows.append(f"    <tr>{cells}</tr>")

    return f"<table>\n  <tbody>\n{chr(10).join(rows)}\n  </tbody>\n</table>\n"


def render_page(title, body_html, css_path, home_href=None):
    home_link = f"<p class=\"breadcrumb\"><a href=\"{home_href}\">Home</a></p>\n" if home_href else ""
    return f"""<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>{html_escape(title)}</title>
    <link rel="stylesheet" href="{css_path}" />
  </head>
  <body>
    <div class="page-container">
      <header>
        <p class="site-meta">ModsCraft MCPE downloads • Minecraft APK archive</p>
        <h1>{html_escape(title)}</h1>
      </header>
      <main class="content">
        {home_link}
        {body_html}
      </main>
      <footer class="footer">
        <p>&copy; {datetime.now(timezone.utc).year} • ModsCraft MCPE archive</p>
      </footer>
    </div>
  </body>
</html>
"""


def local_asset_path(page_path, site_root, asset_name):
    return os.path.relpath(Path(site_root) / asset_name, Path(page_path).parent).replace(os.sep, "/")


def build_main_links(latest_releases):
    main_versions = [k for k in latest_releases if k.startswith("1.") and k != "1.26"]
    if any(k.startswith("26.") for k in latest_releases):
        main_versions.append("26")

    sorted_versions = sorted(
        main_versions,
        key=lambda x: parse_version(x) if x != "26" else [1, 26],
        reverse=True,
    )

    links = []
    for title in sorted_versions:
        if title == "26":
            path = "version/26/index.html"
        else:
            path = f"version/{title.replace('.', '/')}/mc{pathify(latest_releases[title][0])}.html"
        links.append(f"<strong><a href=\"{path}\">📦 Minecraft {html_escape(title)}</a></strong>")

    return create_html_grid(links)


def build_26_index(twenty_six_versions):
    links = []
    for _, (version, _) in sorted(twenty_six_versions.items(), key=lambda x: parse_version(x[0]), reverse=True):
        minor = version.split(".")[1]
        links.append(
            f"<strong><a href=\"{minor}/mc{pathify(version)}.html\">📦 Minecraft {html_escape(version)}</a></strong>"
        )
    return create_html_grid(links)


def render_download_table(downloads):
    rows = []
    for name, link, size in downloads:
        rows.append(
            "      <tr>"
            f"<td><a href=\"{html_escape(link)}\">📦 <code>{html_escape(name)}</code></a></td>"
            f"<td>💾 {html_escape(size)}</td>"
            "</tr>\n"
        )
    return (
        "<table>\n"
        "  <thead>\n"
        "    <tr><th>Download</th><th>Size</th></tr>\n"
        "  </thead>\n"
        "  <tbody>\n"
        + "".join(rows)
        + "  </tbody>\n</table>\n"
    )


user_agents = [
    "Mozilla/5.0 (Linux; Android 13; SM-M127G Build/TP1A.220624.014; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/126.0.6478.134 Mobile Safari/537.36",
    "Mozilla/5.0 (Android 11; Mobile; rv:128.0) Gecko/128.0 Firefox/128.0",
    "Mozilla/5.0 (Linux; Android 10; Pixel 3) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Mobile Safari/537.36",
]

user_agent = random.choice(user_agents)
print(f"* Starting Parser (UA: {user_agent})")

output_file = Path(sys.argv[1])
site_root = output_file.parent
if site_root.exists():
    if site_root.resolve() == Path.cwd().resolve():
        print("* Output path is at repository root; skipping directory removal")
    else:
        print("* Removing existing static site directory")
        shutil.rmtree(site_root)
site_root.mkdir(parents=True, exist_ok=True)

style_source = Path(__file__).resolve().parent / "style.css"
if style_source.exists():
    shutil.copy(style_source, site_root / "style.css")

print("* Getting releases")
resp = requests.get("https://modscraft.net/en/mcpe/", headers={"User-Agent": user_agent})
if not resp.ok:
    print(f"! Failed to fetch main page: {resp.status_code}")
    sys.exit(1)

soup = bs4.BeautifulSoup(resp.text, "html.parser")
releases = {}
carousel = soup.find("div", class_="versions-history-carousel")
if carousel:
    for card in carousel.find_all("div", class_="version-card"):
        a = card.find("a")
        version_span = a.find("span", class_="version-number") if a else None
        if version_span and a and a.has_attr("href"):
            version = version_span.text.replace("Version ", "").strip()
            releases[version] = a["href"]

for article in soup.find_all("article", class_="shortstory"):
    h2 = article.find("h2")
    if h2 and h2.text.startswith("Minecraft "):
        version = h2.text.replace("Minecraft ", "").strip()
        a = article.find("a")
        if a and a.has_attr("href"):
            releases[version] = a["href"]


grouped = {}
for version, url in releases.items():
    parts = version.split(".")
    if len(parts) >= 2:
        key = f"{parts[0]}.{parts[1]}"
        grouped.setdefault(key, []).append((version, url))

latest_releases = {}
for key, vers in grouped.items():
    sorted_vers = sorted(vers, key=lambda x: parse_version(x[0]))
    latest_releases[key] = sorted_vers[-1]


twenty_six_versions = {k: v for k, v in latest_releases.items() if k.startswith("26.")}
if twenty_six_versions:
    index_dir = site_root / "version" / "26"
    index_dir.mkdir(parents=True, exist_ok=True)
    body_html = "<p>All Minecraft 26 versions.</p>\n" + build_26_index(twenty_six_versions)
    page_path = index_dir / "index.html"
    css_path = local_asset_path(page_path, site_root, "style.css")
    home_href = local_asset_path(page_path, site_root, "index.html")
    page_html = render_page("Minecraft 26 Versions", body_html, css_path, home_href)
    page_path.write_text(page_html, encoding="utf-8")

releases = {version: url for version, url in latest_releases.values()}
for title, release in releases.items():
    print(f"* Parsing {title}...", end="\r")
    ver = requests.get(release, headers={"User-Agent": user_agent})
    if not ver.ok:
        print(f"! Skipping {title} (Error {ver.status_code})")
        continue

    rel_soup = bs4.BeautifulSoup(ver.text, "html.parser")
    file_info = []
    for download in rel_soup.find_all("div", class_="file-block"):
        title_span = download.find("span", class_="file-block__title")
        filename_span = download.find("span", class_="file-block__filename")
        meta_div = download.find("div", class_="file-block__meta")
        btn_a = download.find("a", class_="file-block__btn")
        if not (title_span and meta_div and btn_a and btn_a.has_attr("href")):
            print("Skipping incomplete file-block")
            continue

        file_name = (
            filename_span.text.strip()
            if filename_span
            else title_span.text.replace("Download ", "").replace("Minecraft ", "minecraft-").replace(" ", "-").lower() + ".apk"
        )
        size = meta_div.text.split("]")[0][1:].strip()
        file_info.append((file_name, btn_a["href"], size))

    parts = title.split(".")
    if len(parts) >= 2:
        page_dir = site_root / "version" / parts[0] / parts[1]
    else:
        page_dir = site_root / "version"
    page_dir.mkdir(parents=True, exist_ok=True)

    page_path = page_dir / f"mc{pathify(title)}.html"
    css_path = local_asset_path(page_path, site_root, "style.css")
    home_href = local_asset_path(page_path, site_root, "index.html")

    body_html = (
        "<ul>"
        f"<li>📁 Source available at <a href=\"https://modscraft.net/en/mcpe/\"><strong>ModsCraft.Net</strong></a></li>"
        f"<li>🕒 Updated <strong>every 72 hours</strong> at <code>00:00 UTC</code></li>"
        f"<li>🚀 Last update: <code>{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC</code></li>"
        "</ul>\n"
        + render_download_table(file_info)
    )
    page_html = render_page(f"Minecraft {title} APKs", body_html, css_path, home_href)
    page_path.write_text(page_html, encoding="utf-8")

print("* Writing main index")
main_body = (
    "<ul>"
    "<li>📁 Source available at <a href=\"https://modscraft.net/en/mcpe/\"><strong>ModsCraft.Net</strong></a></li>"
    "<li>🕒 Updated <strong>every 72 hours</strong> at <code>00:00 UTC</code></li>"
    f"<li>🚀 Last update: <code>{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC</code></li>"
    "</ul>\n"
    "<h2>Available Major Versions</h2>\n"
    + build_main_links(latest_releases)
)
index_html = render_page("ModsCraft MCPE downloads", main_body, local_asset_path(output_file, site_root, "style.css"))
output_file.write_text(index_html, encoding="utf-8")

print(f"\n* Successfully generated static site to '{output_file}'")
