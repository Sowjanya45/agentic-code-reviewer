"""GitHub App authentication: exchange the App's identity (App ID + private
key) for a short-lived installation access token scoped to whichever repos
a specific installation covers. This is what lets the server act on any
repo an installation covers, without needing a personal token per repo.

Uses PyGithub's built-in App auth (github.Auth.AppAuth) rather than hand-
rolling JWT signing -- it's the same dependency the rest of the reviewer
already uses to talk to the GitHub API.
"""
from __future__ import annotations

import os

from github import Auth, GithubIntegration


def _integration() -> GithubIntegration:
    app_id = os.environ["GITHUB_APP_ID"]
    private_key = os.environ["GITHUB_APP_PRIVATE_KEY"]
    return GithubIntegration(auth=Auth.AppAuth(app_id, private_key))


def get_installation_token(installation_id: int) -> str:
    """Mint a short-lived (~1hr) token scoped to this installation's repos."""
    access_token = _integration().get_access_token(installation_id)
    return access_token.token
