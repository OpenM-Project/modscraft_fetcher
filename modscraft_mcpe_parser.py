import re
import os
import random
import shutil
import sys
from datetime import datetime, timezone

import bs4
import cloudscraper
requests = cloudscraper.create_scraper()

if len(sys.argv) != 2:
    print(f"Error: This program needs 1 argument, got {len(sys.argv) - 1}\n")
    print(f"Usage: {sys.argv[0]} <file-to-write-to>\n")
    print("Parses all MCPE releases from Modscraft and writes to specified Markdown file.")
    sys.exit(1)

def pathify(string):
    return re.sub(r'[^a-z0-9_.-]', '', string.replace(' ', '_').lower())

def create_md_grid(data, cols=3):
    """Creates a clean markdown grid table with invisible headers."""
    if not data:
        return ""
    header = "| " + " | ".join([" " for _ in range(cols)]) + " |\n"
    sep = "| " + " | ".join(["---" for _ in range(cols)]) + " |\n"
    rows = []
    for i in range(0, len(data), cols):
        chunk = data[i:i + cols]
        chunk += [""] * (cols - len(chunk))
        rows.append("| " + " | ".join(chunk) + " |")
    return f"\n{header}{sep}" + "\n".join(rows) + "\n\n"

FRONT_MATTER = "---\nlayout: default\n---\n\n"

user_agents = [
    "Mozilla/5.0 (Linux; Android 13; SM-M127G Build/TP1A.220624.014; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/126.0.6478.134 Mobile Safari/537.36",
    "Mozilla/5.0 (Android 11; Mobile; rv:128.0) Gecko/128.0 Firefox/128.0",
    "Mozilla/5.0 (Linux; Android 10; Pixel 3) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Mobile Safari/537.36"
]

user_agent = random.choice(user_agents)
print(f"* Starting Parser (UA: {user_agent})")

markdown_output = FRONT_MATTER
markdown_output += f"# MCPE Archive\n\n"
markdown_output += f"- :open_file_folder: Source: **ModsCraft.Net**\n"
markdown_output += f"- :clock2: Updated: `every 72 hours`\n"
markdown_output += f"- :rocket: Last update: `{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC`\n\n"

writedir = os.path.dirname(sys.argv[1])
version_dir = os.path.join(writedir, "version")

if os.path.exists(version_dir):
    print("* Removing existing version directory")
    shutil.rmtree(version_dir)
os.makedirs(version_dir, exist_ok=True)

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
        if version_span:
            version = version_span.text.replace("Version ", "").strip()
            releases[version] = a["href"]

for article in soup.find_all("article", class_="shortstory"):
    h2 = article.find("h2")
    if h2 and h2.text.startswith("Minecraft "):
        version = h2.text.replace("Minecraft ", "").strip()
        a = article.find("a")
        if a and "href" in a.attrs:
            releases[version] = a["href"]

def parse_version(v):
    """Converts version strings to sortable lists of ints."""
    parts = []
    for p in v.split('.'):
        if '/' in p:
            p = p.split('/')[0]
        try:
            parts.append(int(p))
        except ValueError:
            parts.append(0)
    return parts

def build_main_links(latest_releases, version_prefix=""):
    """Builds the index grid of major versions."""
    old_titles = [k for k in latest_releases if k.startswith('1.') and k != '1.26']
    if any(k.startswith('26.') for k in latest_releases):
        old_titles.append('26')
    
    sorted_old = sorted(old_titles, key=lambda x: parse_version(x) if x != '26' else [1, 26], reverse=True)
    old_links = []
    
    for title in sorted_old:
        path = f"{version_prefix}26/" if title == '26' else f"{version_prefix}{title.replace('.', '/')}/mc{pathify(latest_releases[title][0])}.html"
        old_links.append(f"**:package: Minecraft {title}**")
    return create_md_grid(old_links)

grouped = {}
for version, url in releases.items():
    parts = version.split('.')
    if len(parts) >= 2:
        key = f"{parts[0]}.{parts[1]}"
        grouped.setdefault(key, []).append((version, url))

latest_releases = {}
for key, vers in grouped.items():
    sorted_vers = sorted(vers, key=lambda x: parse_version(x[0]))
    latest_releases[key] = sorted_vers[-1]

twenty_six_versions = {k: v for k, v in latest_releases.items() if k.startswith('26.')}
if twenty_six_versions:
    os.makedirs(os.path.join(writedir, "version", "26"), exist_ok=True)
    markdown_26 = FRONT_MATTER + "## Minecraft 26 Versions\n\n"
    links_26 = []
    for key, (version, url) in sorted(twenty_six_versions.items(), key=lambda x: parse_version(x[0]), reverse=True):
        minor = version.split('.')[1]
        links_26.append(f"**:package: Minecraft {version}}.html)**")
    markdown_26 += create_md_grid(links_26)
    with open(os.path.join(writedir, "version", "26", "index.md"), "w") as f:
        f.write(markdown_26)

releases = {version: url for version, url in latest_releases.values()}
for title, release in releases.items():
    print(f"* Parsing {title}...", end='\r')
    ver = requests.get(release, headers={"User-Agent": user_agent})
    if not ver.ok:
        print(f"! Skipping {title} (Error {ver.status_code})")
        continue

    rel_soup = bs4.BeautifulSoup(ver.text, "html.parser")
    version_output = FRONT_MATTER + f"## Minecraft {title} APKs\n\n"
    file_info = []
    
    for download in rel_soup.find_all("div", class_="file-block"):
        title_span = download.find("span", class_="file-block__title")
        filename_span = download.find("span", class_="file-block__filename")
        meta_div = download.find("div", class_="file-block__meta")
        btn_a = download.find("a", class_="file-block__btn")
        if not (title_span and meta_div and btn_a):
            print("Skipping incomplete file-block")
            continue

        file_name = filename_span.text if filename_span else title_span.text.replace("Download ", "").replace("Minecraft ", "minecraft-").replace(" ", "-").lower() + ".apk"
        size = meta_div.text.split(']')[0][1:].strip()
        
        # Formatted card with Package icon, Link, and Floppy icon for size
        file_info.append(f"**[:package: `{file_name}`]({btn_a['href']})**<br>**:floppy_disk: {size}**")

    version_output += create_md_grid(file_info)
    
    parts = title.split('.')
    if len(parts) >= 2:
        subdir = os.path.join(writedir, "version", parts[0], parts[1])
        os.makedirs(subdir, exist_ok=True)
        file_path = os.path.join(subdir, f"mc{pathify(title)}.md")
    else:
        file_path = os.path.join(writedir, "version", f"mc{pathify(title)}.md")
    
    with open(file_path, "w") as f:
        f.write(version_output)

markdown_output += f"## Available Major Versions\n\n"
markdown_output += build_main_links(latest_releases, 'version/')

with open(os.path.join(sys.argv[1]), "w") as f:
    f.write(markdown_output)

print(f"\n* Successfully generated site to '{sys.argv[1]}'")
