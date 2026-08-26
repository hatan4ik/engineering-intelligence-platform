import re

filepath = 'app/main.py'
with open(filepath, 'r') as f:
    content = f.read()

old_recorder = """        if recorder is not None:
            recorder.record_pr_closed(
                repository=str(terminal["repository"]),
                pr_number=int(terminal["pr_number"]),
                service=None,
                merged=bool(terminal["merged"]),
            )"""

new_recorder = """        if recorder is not None:
            recorder.record_pr_closed(
                repository=str(terminal["repository"]),
                pr_number=int(terminal["pr_number"]),
                service=None,
                merged=bool(terminal["merged"]),
                risk_signal=str(terminal.get("risk_signal", "not-reviewed")),
                utility_signal=str(terminal.get("utility_signal", "not-reviewed")),
            )"""

content = content.replace(old_recorder, new_recorder)

with open(filepath, 'w') as f:
    f.write(content)
