from eval.matching import bug_is_caught, count_matching_findings, finding_matches_bug
from mining.dataset import BugPair
from reviewer.schema import Finding


def _bug(**overrides) -> BugPair:
    base = dict(
        repo="local", repo_url="local", fix_commit="f" * 40, fix_summary="fix",
        bug_commit="b" * 40, file="a.py", line_start=10, line_end=12, matched_lines=1,
    )
    base.update(overrides)
    return BugPair(**base)


def _finding(**overrides) -> Finding:
    base = dict(
        file="a.py", line_start=10, line_end=10, category="logic", severity="warning",
        confidence=0.5, summary="s", detail="d",
    )
    base.update(overrides)
    return Finding(**base)


def test_exact_overlap_matches():
    assert finding_matches_bug(_finding(), _bug())


def test_different_file_never_matches():
    assert not finding_matches_bug(_finding(file="b.py"), _bug())


def test_within_tolerance_matches():
    # bug is lines 10-12, finding at line 14 is within the 3-line tolerance
    assert finding_matches_bug(_finding(line_start=14, line_end=14), _bug())


def test_far_away_does_not_match():
    assert not finding_matches_bug(_finding(line_start=100, line_end=100), _bug())


def test_bug_is_caught_true_if_any_finding_matches():
    findings = [_finding(line_start=100, line_end=100), _finding(line_start=11, line_end=11)]
    assert bug_is_caught(findings, _bug())


def test_bug_is_caught_false_if_none_match():
    findings = [_finding(line_start=100, line_end=100)]
    assert not bug_is_caught(findings, _bug())


def test_count_matching_findings():
    findings = [_finding(line_start=10, line_end=10), _finding(line_start=11, line_end=11), _finding(line_start=100, line_end=100)]
    assert count_matching_findings(findings, _bug()) == 2
