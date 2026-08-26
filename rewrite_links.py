import os

replacements = {
    'architecture/adr/001-temporal-control-plane.md': 'architecture/adr/001-temporal-control-plane.md',
    'adr/001-temporal-control-plane.md': 'adr/001-temporal-control-plane.md',
    'architecture/milestones/milestones/p1-secure-azure-foundation.md': 'architecture/milestones/milestones/p1-secure-azure-foundation.md',
    'milestones/p1-secure-azure-foundation.md': 'milestones/milestones/p1-secure-azure-foundation.md',
    'architecture/milestones/milestones/m3-production-ingestion.md': 'architecture/milestones/milestones/m3-production-ingestion.md',
    'milestones/m3-production-ingestion.md': 'milestones/milestones/m3-production-ingestion.md',
    'architecture/milestones/milestones/vertical-slice.md': 'architecture/milestones/milestones/vertical-slice.md',
    'milestones/vertical-slice.md': 'milestones/milestones/vertical-slice.md',
    'faang-multi-cloud-and-on-prem-extensions.md': 'faang-multi-cloud-and-on-prem-extensions.md',
    'alignment-review.md': 'alignment-review.md',
    'capability-reconciliation.md': 'capability-reconciliation.md',
    'maturity-scorecard.md': 'maturity-scorecard.md',
    'non-functional-requirements.md': 'non-functional-requirements.md',
    'design.md': 'design.md'
}

for root, _, files in os.walk('.'):
    for f in files:
        if f.endswith('.md') or f.endswith('.py') or f == 'README.md':
            path = os.path.join(root, f)
            with open(path, 'r') as file:
                content = file.read()
            
            new_content = content
            for old, new in replacements.items():
                new_content = new_content.replace(old, new)
                
            if new_content != content:
                with open(path, 'w') as file:
                    file.write(new_content)
                print(f"Updated {path}")
