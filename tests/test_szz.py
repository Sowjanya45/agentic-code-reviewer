from pathlib import Path

import git
from git import Actor

from mining.szz import find_fixing_commits, mine_bug_pairs

_AUTHOR = Actor("Test", "test@example.com")


def _commit(repo: git.Repo, path: Path, filename: str, content: str, message: str) -> git.Commit:
    (path / filename).write_text(content)
    repo.index.add([filename])
    return repo.index.commit(message, author=_AUTHOR, committer=_AUTHOR)


def _make_repo_with_bug_and_fix(tmp_path: Path) -> tuple[git.Repo, git.Commit, git.Commit]:
    repo = git.Repo.init(tmp_path)

    _commit(
        repo, tmp_path, "calc.py",
        "def add(a, b):\n    return a + b\n",
        "Initial commit",
    )

    buggy_content = (
        "def add(a, b):\n"
        "    return a + b\n"
        "\n"
        "def calculate(x):\n"
        "    if x > 0:\n"
        "        return x - 1\n"
        "    return x\n"
    )
    bug_commit = _commit(repo, tmp_path, "calc.py", buggy_content, "Add calculate function")

    fixed_content = (
        "def add(a, b):\n"
        "    return a + b\n"
        "\n"
        "def calculate(x):\n"
        "    if x > 0:\n"
        "        return x\n"
        "    return x\n"
    )
    fix_commit = _commit(repo, tmp_path, "calc.py", fixed_content, "Fix off-by-one error in calculate")

    return repo, bug_commit, fix_commit


def test_find_fixing_commits_matches_fix_keyword(tmp_path: Path):
    repo, _, fix_commit = _make_repo_with_bug_and_fix(tmp_path)
    fixing = find_fixing_commits(repo)
    assert [c.hexsha for c, _ in fixing] == [fix_commit.hexsha]


def test_mine_bug_pairs_identifies_the_introducing_commit(tmp_path: Path):
    repo, bug_commit, fix_commit = _make_repo_with_bug_and_fix(tmp_path)
    pairs = mine_bug_pairs(repo, repo_url="local", repo_local_path=str(tmp_path))

    assert len(pairs) == 1
    pair = pairs[0]
    assert pair.bug_commit == bug_commit.hexsha
    assert pair.fix_commit == fix_commit.hexsha
    assert pair.file == "calc.py"
    assert pair.line_start == 6
    assert pair.line_end == 6


def test_root_commit_is_never_returned_as_bug_commit(tmp_path: Path):
    # A fix touching a line from the very first commit should be skipped,
    # since the root commit can't be "reviewed" as a diff against a parent.
    repo = git.Repo.init(tmp_path)
    _commit(
        repo, tmp_path, "calc.py",
        "def calculate(x):\n    return x - 1\n",
        "Initial commit (already buggy)",
    )
    _commit(
        repo, tmp_path, "calc.py",
        "def calculate(x):\n    return x\n",
        "Fix off-by-one error",
    )
    pairs = mine_bug_pairs(repo, repo_url="local", repo_local_path=str(tmp_path))
    assert pairs == []
