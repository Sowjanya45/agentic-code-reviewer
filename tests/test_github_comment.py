from reviewer.github_comment import post_review_comment


def test_posts_body_as_issue_comment_on_the_pr(mocker):
    mock_pr = mocker.Mock()
    mock_repo = mocker.Mock()
    mock_repo.get_pull.return_value = mock_pr
    mock_gh_instance = mocker.Mock()
    mock_gh_instance.get_repo.return_value = mock_repo
    mock_gh_class = mocker.patch("reviewer.github_comment.Github", return_value=mock_gh_instance)

    post_review_comment("owner/repo", 42, "tok", "hello world")

    mock_gh_class.assert_called_once_with("tok")
    mock_gh_instance.get_repo.assert_called_once_with("owner/repo")
    mock_repo.get_pull.assert_called_once_with(42)
    mock_pr.create_issue_comment.assert_called_once_with("hello world")
