import re
import os
from pathlib import Path

def check_file(filepath):
    content = Path(filepath).read_text()
    links = re.findall(r'\[.*?\]\((.*?)\)', content)
    base_dir = Path(filepath).parent
    for link in links:
        if link.startswith('http') or link.startswith('#'):
            continue
        target = (base_dir / link).resolve()
        if not target.exists():
            print(f"Broken link in {filepath}: {link} -> {target}")

for root, _, files in os.walk('.'):
    for f in files:
        if f.endswith('.md'):
            check_file(os.path.join(root, f))
