import re
import os
from pathlib import Path

def normalize_header(header):
    return '#' + re.sub(r'[^a-z0-9\-]', '', header.lower().replace(' ', '-'))

def check_anchors(filepath):
    content = Path(filepath).read_text()
    headers = [normalize_header(m.group(1)) for m in re.finditer(r'^#+\s+(.*?)$', content, flags=re.MULTILINE)]
    links = re.findall(r'\[.*?\]\((#.*?)\)', content)
    for link in links:
        if link not in headers:
            print(f"Broken anchor in {filepath}: {link}")

for root, _, files in os.walk('.'):
    for f in files:
        if f.endswith('.md'):
            check_anchors(os.path.join(root, f))
