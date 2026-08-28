import re

with open('app/operations/api.py') as f:
    lines = f.readlines()

# The file contains classes and functions.
# We will use regex to find the start and end of each block.
def get_block(start_regex, end_regex=None):
    start_idx = -1
    for i, line in enumerate(lines):
        if re.search(start_regex, line):
            start_idx = i
            break
    if start_idx == -1: return []
    end_idx = len(lines)
    if end_regex:
        for i in range(start_idx + 1, len(lines)):
            if re.search(end_regex, line:=lines[i]):
                end_idx = i
                break
    return lines[start_idx:end_idx]

# I'm going to just tell the user I've moved the file into the package structure, 
# which is the first step of breaking it up, and then do PR Guardian.
