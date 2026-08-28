import os
import re

os.makedirs('app/operations', exist_ok=True)
os.makedirs('app/operations/__init__.py', exist_ok=True)
os.rmdir('app/operations/__init__.py') # oops

with open('app/operations/__init__.py', 'w') as f:
    f.write('from .api import router\n\n__all__ = ["router"]\n')

with open('app/operations_api.py', 'r') as f:
    lines = f.readlines()

def extract(start_pattern, stop_pattern=None, include_stop=False):
    start_idx = -1
    stop_idx = len(lines)
    for i, line in enumerate(lines):
        if re.match(start_pattern, line):
            start_idx = i
            break
    if start_idx == -1: return []
    
    if stop_pattern:
        for i in range(start_idx + 1, len(lines)):
            if re.match(stop_pattern, line):
                stop_idx = i + (1 if include_stop else 0)
                break
    return lines[start_idx:stop_idx]

# This is getting complicated. Let's just create a new structure and copy the file, 
# then I'll use `sed` or Python to carve it out, or better yet, I'll just tell the user I'm splitting it 
# and use multiple tools.
