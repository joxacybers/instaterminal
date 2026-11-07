"""Automated tests for 100% Real InstaTerminal CLI and Instagram profile fetcher."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from instaterminal.app import (
    render_highlight_stories_to_terminal,
    render_profile_to_terminal,
)
from instaterminal.core.client import InstaClientService
from instaterminal.core.image_renderer import TerminalImageRenderer


def test_real_profile_fetch_authenticated_session(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify live Instagram profile fetching using saved session (zero mock data)."""
    monkeypatch.setenv("INSTATERMINAL_HOME", str(tmp_path))
    service = InstaClientService()
    assert service.ensure_default_session() is True
    assert service.username != ""

    profile = service.fetch_real_profile(service.username, download_media=True)
    assert profile.username == service.username
    assert profile.user_id.isdigit()
    assert profile.profile_link == f"https://www.instagram.com/{service.username}/"


def test_real_profile_fetch_with_posts_and_highlights(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify live Instagram profile, highlights, and posts fetching for @durov."""
    monkeypatch.setenv("INSTATERMINAL_HOME", str(tmp_path))
    service = InstaClientService()
    profile = service.fetch_real_profile("durov", download_media=False)

    assert profile.username == "durov"
    assert profile.user_id == "4663052"
    assert profile.full_name == "Pavel Durov"
    assert profile.is_verified is True
    assert profile.follower_count > 1_000_000
    assert profile.media_count > 50
    assert len(profile.posts) >= 6
    assert profile.posts[0].code != ""
    assert profile.posts[0].post_url.startswith("https://www.instagram.com/p/")

    # Ensure terminal renderer runs cleanly on real profile
    render_profile_to_terminal(profile, show_post_images=False)


def test_real_highlight_stories_and_download(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify fetching real Highlight stories (photo + MP4 video) and downloading them."""
    monkeypatch.setenv("INSTATERMINAL_HOME", str(tmp_path))
    service = InstaClientService()
    hl = service.fetch_highlight_stories("17949310159991350", download_previews=True)

    assert hl.id == "17949310159991350"
    assert hl.title == "Up and Up"
    assert len(hl.items) >= 2
    render_highlight_stories_to_terminal(hl)

    saved_photo = service.download_story_item(
        hl.items[0],
        highlight_id=hl.id,
        highlight_title=hl.title,
        owner_username=hl.owner_username,
    )
    assert saved_photo is not None and saved_photo.exists()
    assert saved_photo.suffix == ".jpg"
    assert "highlight" in saved_photo.parts

    # Also test unverified profile highlight fallback (@nastarn_0000000007 -> 18123920284924707)
    prof_n = service.fetch_real_profile("nastarn_0000000007", download_media=False)
    assert len(prof_n.highlights) >= 1
    hl_n = service.fetch_highlight_stories(
        prof_n.highlights[0].id,
        fallback_highlight=prof_n.highlights[0],
    )
    saved_n = service.download_all_highlight_stories(hl_n)
    assert len(saved_n) >= 1
    assert saved_n[0].exists()
    assert "@nastarn_0000000007" in saved_n[0].parts
    assert "highlight" in saved_n[0].parts


def test_real_followers_and_following(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify fetching real followers and following users and exporting them into @<username>/followers/."""
    monkeypatch.setenv("INSTATERMINAL_HOME", str(tmp_path))
    service = InstaClientService()
    service.ensure_default_session()
    followers = service.get_user_followers("nastarn_0000000007", amount=5)
    assert len(followers) >= 1
    assert followers[0].username != ""

    following = service.get_user_following("nastarn_0000000007", amount=5)
    assert len(following) >= 1
    assert following[0].username != ""

    exported = service.export_user_list(
        "nastarn_0000000007",
        "followers",
        followers,
    )
    assert len(exported) == 2
    assert exported[0].exists() and exported[1].exists()
    assert "@nastarn_0000000007" in exported[0].parts
    assert "followers" in exported[0].parts


def test_download_everything_for_profile(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify full profile archive downloading into @<username>/<category>/ subfolders."""
    service = InstaClientService()
    service.ensure_default_session()
    monkeypatch.setenv("INSTATERMINAL_HOME", str(tmp_path))

    profile = service.fetch_real_profile("allayorovvvv_7", download_media=True)
    results = service.download_everything_for_profile(profile, include_followers=False)

    assert len(results["info"]) == 2
    assert "@allayorovvvv_7" in results["info"][0].parts
    assert "info" in results["info"][0].parts

    assert len(results["avatar"]) == 1
    assert "@allayorovvvv_7" in results["avatar"][0].parts
    assert "avatar" in results["avatar"][0].parts

    assert len(results["posts_and_reels"]) >= 1
    assert results["posts_and_reels"][0].exists()
    assert "@allayorovvvv_7" in results["posts_and_reels"][0].parts
    assert any(cat in results["posts_and_reels"][0].parts for cat in ("posts", "reels"))


def test_cli_command_invocation() -> None:
    """Verify that `instaterminal` CLI command and `python -m instaterminal` work."""
    res_mod = subprocess.run(
        [sys.executable, "-m", "instaterminal", "--version"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "InstaTerminal v1.0.0" in res_mod.stdout

    res_bin = subprocess.run(
        ["instaterminal", "--version"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "InstaTerminal v1.0.0" in res_bin.stdout
