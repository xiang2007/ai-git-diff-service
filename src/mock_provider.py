import re

from unidiff.patch import PatchSet


HARDCODED_CREDENTIAL_RE = re.compile(
    r"(api[_-]?key|secret|token)\s*[:=]\s*['\"][A-Za-z0-9_\-]{16,}['\"]",
    re.IGNORECASE,
)
SQL_IN_STRING_RE = re.compile(r"""['"][^'"]*\b(?:SELECT|INSERT|UPDATE|DELETE)\b[^'"]*['"]""")
INJECTION_PATTERNS = ("ignore previous instructions", "disregard all prior", "you are now")


def _empty_catch(text: str, target_lines: list[str], index: int) -> bool:
    """Return True when an added catch statement has an empty body."""
    catch_match = re.search(r"\bcatch\b", text) # match the word catch
    if not catch_match:
        return False
    line_index = index
    current_text = text
    search_from = catch_match.end() # starts after catch "}catch(error){" '}' will get ignore
    while True:
        open_index = current_text.find("{", search_from)
        if open_index != -1:
            break
        line_index += 1
        if line_index >= len(target_lines):
            return False
        current_text = target_lines[line_index]
        search_from = 0
        # Before the opening brace, only blank lines are acceptable.
        if current_text.strip() and not current_text.lstrip().startswith("{"):
            return False
    # Scan until the matching closing brace.
    depth = 1
    body_parts: list[str] = []
    current_text = current_text[open_index + 1:]
    while True:
        for character in current_text:
            if character == "{":
                depth += 1
                body_parts.append(character)
            elif character == "}":
                depth -= 1
                if depth == 0:
                    # if result after strip is empty, then MOCK-004
                    return "".join(body_parts).strip() == ""
                body_parts.append(character)
            else:
                body_parts.append(character)
        line_index += 1
        if line_index >= len(target_lines):
            return False
        body_parts.append("\n")
        current_text = target_lines[line_index]


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
    findings_by_id: dict[str, dict] = {}
    for patched_file in patch:
        for hunk in patched_file:
            # Target-side lines consist of additions and unchanged context.
            # Removed lines do not exist in the resulting file.
            target_lines = [
                line.value.rstrip("\r\n")
                for line in hunk
                if not line.is_removed
            ]
            target_line_numbers = [
                line.target_line_no
                for line in hunk
                if not line.is_removed
            ]
            added_flags = [
                line.is_added
                for line in hunk
                if not line.is_removed
            ]
            for index, text in enumerate(target_lines):
                # Rules only apply to added lines.
                if not added_flags[index]:
                    continue
                line_no = target_line_numbers[index]
                for rule in MOCK_RULES:
                    if not rule["match"](text, target_lines, index):
                        continue
                    finding_id = f"{rule['id']}:{patched_file.path}:{line_no}"
                    findings_by_id[finding_id] = {
                        "id": finding_id,
                        "ruleId": rule["id"],
                        "path": patched_file.path,
                        "line": line_no,
                        "severity": rule["severity"],
                        "category": rule["category"],
                        "title": rule["title"],
                        "evidence": text,
                    }
    findings = list(findings_by_id.values())
    findings.sort(key=lambda finding: (
        finding["path"],
        finding["line"],
        finding["ruleId"],
    ))
    return findings
