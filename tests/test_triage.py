from reviewer.diff_ingest import ChangedFile
from reviewer.triage import rank_files_by_risk


def test_auth_file_ranked_above_docs():
    files = [
        ChangedFile(filename="README.md", status="modified", patch="", full_content=""),
        ChangedFile(filename="src/auth/login.py", status="modified", patch="", full_content=""),
        ChangedFile(filename="src/utils/format.py", status="modified", patch="", full_content=""),
    ]
    ranked = rank_files_by_risk(files)
    assert ranked[0].filename == "src/auth/login.py"
    assert ranked[-1].filename == "README.md"
