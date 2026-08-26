import re

filepath = 'product/pr_guardian_service.py'
with open(filepath, 'r') as f:
    content = f.read()

# 1. Update evaluate definition
old_eval = """    def evaluate(self, event: PullRequestEvent, *, publish: bool = True) -> PRGuardianResult:"""
new_eval = """    async def evaluate(self, event: PullRequestEvent, *, publish: bool = True) -> PRGuardianResult:"""
content = content.replace(old_eval, new_eval)

# 2. Update workflows.start_pr_review call
old_call = """        workflow, policy = self.workflows.start_pr_review("""
new_call = """        workflow, policy = await self.workflows.start_pr_review("""
content = content.replace(old_call, new_call)

with open(filepath, 'w') as f:
    f.write(content)
