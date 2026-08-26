import re

filepath = 'app/main.py'
with open(filepath, 'r') as f:
    content = f.read()

old_call = """        result = guardian.evaluate(event)"""
new_call = """        result = await guardian.evaluate(event)"""
content = content.replace(old_call, new_call)

with open(filepath, 'w') as f:
    f.write(content)
