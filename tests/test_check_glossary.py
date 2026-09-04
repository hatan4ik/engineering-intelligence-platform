"""Focused contracts for Company Brain glossary hover-term validation."""

from __future__ import annotations

from check_glossary import find_hover_term_failures, glossary_entries, prose_only


def test_glossary_entries_reads_term_and_autonomy_tables() -> None:
    content = """
| Term | Expansion | Meaning |
|---|---|---|
| AKS | Azure Kubernetes Service | Managed Kubernetes |

| Level | Expansion | Meaning |
|---|---|---|
| L4 | Autonomy Level 4 — bounded autonomous | Certified execution |
"""

    assert glossary_entries(content) == {
        "AKS": "Azure Kubernetes Service",
        "L4": "Autonomy Level 4 — bounded autonomous",
    }


def test_hover_terms_require_the_canonical_expansion() -> None:
    definitions = {"AKS": "Azure Kubernetes Service"}
    content = '<span title="Azure Kubernetes Service">AKS</span> <span title="wrong">AKS</span>'

    assert find_hover_term_failures("docs/example.md", content, definitions) == [
        "Glossary hover title mismatch in docs/example.md: AKS uses 'wrong'; "
        "expected 'Azure Kubernetes Service'"
    ]


def test_hover_terms_must_be_registered_in_the_glossary() -> None:
    content = '<span title="Unregistered expansion">UNKNOWN</span>'

    assert find_hover_term_failures("docs/example.md", content, {}) == [
        "Unknown glossary hover term in docs/example.md: UNKNOWN"
    ]


def test_hover_terms_do_not_validate_literal_code_examples() -> None:
    content = """
```html
<span title="Expansion">TERM</span>
```
`<span title="Expansion">TERM</span>`
<span title="Azure Kubernetes Service">AKS</span>
"""

    assert prose_only(content) == '<span title="Azure Kubernetes Service">AKS</span>'
    assert find_hover_term_failures(
        "docs/example.md", content, {"AKS": "Azure Kubernetes Service"}
    ) == []
