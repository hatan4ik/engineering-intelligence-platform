import re

with open('product/pr_guardian_service.py', 'r') as f:
    lines = f.readlines()

# It's actually safer to just write the new decomposed class and replace the old one.
