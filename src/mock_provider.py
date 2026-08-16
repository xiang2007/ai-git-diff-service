import re

from unidiff.patch import PatchSet


HARDCODED_CREDENTIAL_RE = re.compile(
    r"(api[_-]?key|secret|token)\s*[:=]\s*['\"][A-Za-z0-9_\-]{16,}['\"]",
    re.IGNORECASE,
)
SQL_IN_STRING_RE = re.compile(r"""['"][^'"]*\b(?:SELECT|INSERT|UPDATE|DELETE)\b[^'"]*['"]""")
INJECTION_PATTERNS = ("ignore previous instructions", "disregard all prior", "you are now")


def _empty_catch(text: str, added: list[str], index: int) -> bool:
    """True if an added `catch` line opens a block that is empty (possibly across lines)."""
    match = re.search(r"\bcatch\b", text)
    if not match:
        return False
    open_idx = text.find("{", match.start())
    if open_idx == -1:
        return False
    body = text[open_idx + 1:]
    i = index
    while "}" not in body and i + 1 < len(added):
        i += 1
        body += "\n" + added[i]
    close_idx = body.find("}")
    if close_idx == -1:
        return False
    return body[:close_idx].strip() == ""


MOCK_RULES = [
    {
        "id": "MOCK-001",
        "severity": "critical",
        "category": "security",
        "title": "eval usage",
        "match": lambda text, added, index: "eval(" in text,
    },
    {
        "id": "MOCK-002",
        "severity": "critical",
        "category": "security",
        "title": "hardcoded credential",
        "match": lambda text, added, index: bool(HARDCODED_CREDENTIAL_RE.search(text)),
    },
    {
        "id": "MOCK-003",
        "severity": "high",
        "category": "security",
        "title": "SQL string concatenation",
        "match": lambda text, added, index: bool(SQL_IN_STRING_RE.search(text)) and "+" in text,
    },
    {
        "id": "MOCK-004",
        "severity": "high",
        "category": "correctness",
        "title": "swallowed exception",
        "match": _empty_catch,
    },
    {
        "id": "MOCK-005",
        "severity": "medium",
        "category": "correctness",
        "title": "loose null comparison",
        "match": lambda text, added, index: "== null" in text or "!= null" in text,
    },
    {
        "id": "MOCK-006",
        "severity": "medium",
        "category": "performance",
        "title": "deep-clone via JSON",
        "match": lambda text, added, index: "JSON.parse(JSON.stringify(" in text,
    },
    {
        "id": "MOCK-007",
        "severity": "low",
        "category": "style",
        "title": "console.log left in",
        "match": lambda text, added, index: "console.log(" in text,
    },
    {
        "id": "MOCK-008",
        "severity": "low",
        "category": "style",
        "title": "unresolved marker",
        "match": lambda text, added, index: "TODO" in text or "FIXME" in text,
    },
    {
        "id": "MOCK-INJ",
        "severity": "critical",
        "category": "security",
        "title": "prompt-injection content",
        "match": lambda text, added, index: any(p in text.lower() for p in INJECTION_PATTERNS),
    },
]


def run_mock_provider(patch: PatchSet) -> list[dict]:
    findings = []
    for file in patch:
        added_lines = []
        for hunk in file:
            for line in hunk:
                if line.is_added:
                    text = line.value.rstrip("\n")
                    added_lines.append((line.target_line_no, text))
        added_texts = [text for _, text in added_lines]
        for index, (line_no, text) in enumerate(added_lines):
            for rule in MOCK_RULES:
                if rule["match"](text, added_texts, index):
                    findings.append(
                        {
                            "id": f"{rule['id']}:{file.path}:{line_no}",
                            "ruleId": rule["id"],
                            "path": file.path,
                            "line": line_no,
                            "severity": rule["severity"],
                            "category": rule["category"],
                            "title": rule["title"],
                            "evidence": text,
                        }
                    )

    findings.sort(key=lambda f: (f["path"], f["line"], f["ruleId"]))

    seen: set[str] = set()
    unique = []
    for finding in findings:
        if finding["id"] not in seen:
            seen.add(finding["id"])
            unique.append(finding)
    return unique
