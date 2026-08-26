import re

filepath = 'feedback/outcome_capture.py'
with open(filepath, 'r') as f:
    content = f.read()

# Replace normalize_github_pr_outcome
old_normalize = """def normalize_github_pr_outcome(payload: Mapping[str, object]) -> dict[str, object] | None:
    \"\"\"Extract only terminal PR outcomes; non-terminal webhook deliveries are ignored.\"\"\"
    if str(payload.get("action", "")) != "closed":
        return None
    repository = payload.get("repository")
    pull_request = payload.get("pull_request")
    if not isinstance(repository, Mapping) or not isinstance(pull_request, Mapping):
        raise ValueError("invalid GitHub pull_request outcome payload")
    full_name = str(repository.get("full_name", "")).strip()
    number = int(payload.get("number", 0))
    if not full_name or number <= 0:
        raise ValueError("missing GitHub repository or PR number")
    return {
        "repository": full_name,
        "pr_number": number,
        "merged": bool(pull_request.get("merged", False)),
    }"""

new_normalize = """def normalize_github_pr_outcome(payload: Mapping[str, object]) -> dict[str, object] | None:
    \"\"\"Extract terminal PR outcomes along with explicit reviewer labels (shadow pilot).\"\"\"
    if str(payload.get("action", "")) != "closed":
        return None
    repository = payload.get("repository")
    pull_request = payload.get("pull_request")
    if not isinstance(repository, Mapping) or not isinstance(pull_request, Mapping):
        raise ValueError("invalid GitHub pull_request outcome payload")
    full_name = str(repository.get("full_name", "")).strip()
    number = int(payload.get("number", 0))
    if not full_name or number <= 0:
        raise ValueError("missing GitHub repository or PR number")
        
    raw_labels = pull_request.get("labels", [])
    labels = [str(l.get("name", "")).lower() for l in raw_labels if isinstance(l, dict)]
    
    risk_labels = [l for l in labels if l in {"eip-pr-guardian/confirmed-risk", "eip-pr-guardian/false-positive"}]
    utility_labels = [l for l in labels if l in {"eip-pr-guardian/useful", "eip-pr-guardian/not-useful"}]
    
    risk_signal = risk_labels[0].replace("eip-pr-guardian/", "") if risk_labels else "not-reviewed"
    utility_signal = utility_labels[0].replace("eip-pr-guardian/", "") if utility_labels else "not-reviewed"

    return {
        "repository": full_name,
        "pr_number": number,
        "merged": bool(pull_request.get("merged", False)),
        "risk_signal": risk_signal,
        "utility_signal": utility_signal,
    }"""

content = content.replace(old_normalize, new_normalize)

# Replace record_pr_closed signature
old_record = """    def record_pr_closed(
        self,
        *,
        repository: str,
        pr_number: int,
        service: str | None,
        merged: bool,
        reverted: bool = False,
        risk_score: int | None = None,
    ) -> CapturedOutcome:"""

new_record = """    def record_pr_closed(
        self,
        *,
        repository: str,
        pr_number: int,
        service: str | None,
        merged: bool,
        reverted: bool = False,
        risk_score: int | None = None,
        risk_signal: str = "not-reviewed",
        utility_signal: str = "not-reviewed",
    ) -> CapturedOutcome:"""
content = content.replace(old_record, new_record)

# Add metadata
old_metadata = """                "pr_number": str(pr_number),
                **({"risk_score": str(risk_score)} if risk_score is not None else {}),"""

new_metadata = """                "pr_number": str(pr_number),
                "risk_signal": risk_signal,
                "utility_signal": utility_signal,
                **({"risk_score": str(risk_score)} if risk_score is not None else {}),"""
content = content.replace(old_metadata, new_metadata)

with open(filepath, 'w') as f:
    f.write(content)
