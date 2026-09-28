from server.github_app_auth import get_installation_token


def test_get_installation_token_uses_app_auth_and_returns_token(monkeypatch, mocker):
    monkeypatch.setenv("GITHUB_APP_ID", "12345")
    monkeypatch.setenv("GITHUB_APP_PRIVATE_KEY", "fake-pem-for-test")

    mock_access_token = mocker.Mock()
    mock_access_token.token = "ghs_installation_token"
    mock_integration_instance = mocker.Mock()
    mock_integration_instance.get_access_token.return_value = mock_access_token
    mocker.patch("server.github_app_auth.GithubIntegration", return_value=mock_integration_instance)
    mock_app_auth = mocker.patch("server.github_app_auth.Auth.AppAuth")

    token = get_installation_token(999)

    mock_app_auth.assert_called_once_with("12345", "fake-pem-for-test")
    mock_integration_instance.get_access_token.assert_called_once_with(999)
    assert token == "ghs_installation_token"
