from reviewer.aggregator import aggregate_findings
from reviewer.schema import Finding


def _finding(**overrides) -> Finding:
    base = dict(
        file="a.py",
        line_start=10,
        line_end=12,
        category="security",
        severity="warning",
        confidence=0.5,
        summary="issue",
        detail="detail",
    )
    base.update(overrides)
    return Finding(**base)


def test_overlapping_same_category_findings_are_deduped_keeping_higher_confidence():
    low = _finding(confidence=0.4)
    high = _finding(confidence=0.9)
    result = aggregate_findings([low, high])
    assert len(result) == 1
    assert result[0].confidence == 0.9


def test_non_overlapping_findings_are_both_kept():
    a = _finding(line_start=1, line_end=2)
    b = _finding(line_start=50, line_end=52)
    result = aggregate_findings([a, b])
    assert len(result) == 2


def test_different_categories_on_same_lines_are_both_kept():
    security = _finding(category="security")
    error_handling = _finding(category="error_handling")
    result = aggregate_findings([security, error_handling])
    assert len(result) == 2


def test_sorted_by_severity_then_confidence():
    nit = _finding(severity="nit", confidence=0.99, line_start=1, line_end=1)
    blocker = _finding(severity="blocker", confidence=0.1, line_start=100, line_end=100)
    result = aggregate_findings([nit, blocker])
    assert result[0].severity == "blocker"
    assert result[1].severity == "nit"
