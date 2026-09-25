"""Match a reviewer's findings against a mined ground-truth bug location."""
from __future__ import annotations

from mining.dataset import BugPair
from reviewer.schema import Finding

_LINE_TOLERANCE = 3  # allow a small drift from imperfect SZZ line matching


def finding_matches_bug(finding: Finding, bug: BugPair) -> bool:
    if finding.file != bug.file:
        return False
    start = bug.line_start - _LINE_TOLERANCE
    end = bug.line_end + _LINE_TOLERANCE
    return finding.line_start <= end and start <= finding.line_end


def bug_is_caught(findings: list[Finding], bug: BugPair) -> bool:
    return any(finding_matches_bug(f, bug) for f in findings)


def count_matching_findings(findings: list[Finding], bug: BugPair) -> int:
    return sum(1 for f in findings if finding_matches_bug(f, bug))
