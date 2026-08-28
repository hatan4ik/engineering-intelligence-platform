lines = open('pyproject.toml', 'r').readlines()
lines = [l for l in lines if l.strip() != "kubernetes"]
with open('pyproject.toml', 'w') as f:
    f.writelines(lines)
