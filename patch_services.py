import os

services = [
    ('product/incident_service.py', 'def investigate(', 'workflow = self.workflows.start_incident('),
    ('product/deployment_failure_service.py', 'def investigate(', 'workflow = self.workflows.start_deployment_failure('),
    ('product/drift_service.py', 'def run(', 'workflow = self.workflows.start_drift_review(')
]

for filepath, def_str, call_str in services:
    with open(filepath, 'r') as f:
        content = f.read()
        
    content = content.replace(def_str, f"async {def_str}")
    content = content.replace(call_str, call_str.replace("self.workflows", "await self.workflows"))
    
    with open(filepath, 'w') as f:
        f.write(content)
