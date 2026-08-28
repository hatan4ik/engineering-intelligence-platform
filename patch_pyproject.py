import re
with open('pyproject.toml', 'r') as f:
    c = f.read()
c = c.replace('"temporalio",\n]', '"temporalio",\n  "kubernetes",\n]')
with open('pyproject.toml', 'w') as f:
    f.write(c)
