"""Configuration and directory paths for InstaTerminal (Desktop & Android Termux)."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path


def is_termux() -> bool:
    """Return True if running inside Android Termux environment."""
    if os.environ.get("TERMUX_VERSION"):
        return True
    prefix = os.environ.get("PREFIX", "")
    if "com.termux" in prefix:
        return True
    return Path("/data/data/com.termux").exists()


def get_app_dir() -> Path:
    """Return the base configuration and cache directory for InstaTerminal."""
    custom_dir = os.environ.get("INSTATERMINAL_HOME")
    if custom_dir:
        base = Path(custom_dir)
    else:
        base = Path.home() / ".instaterminal"
    base.mkdir(parents=True, exist_ok=True)
    return base


def get_session_file() -> Path:
    """Return path to saved instagrapi session file."""
    return get_app_dir() / "session.json"


def get_cache_dir() -> Path:
    """Return directory for cached post/story images."""
    cache = get_app_dir() / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    return cache


def get_downloads_dir() -> Path:
    """
    Return root directory for downloaded media (photos, stories, reels, lists).
    On Android Termux, automatically uses /sdcard/Download/InstaTerminal (or ~/storage/downloads/InstaTerminal)
    when shared storage permission is enabled, so downloaded media appears directly in the phone's Gallery!
    """
    custom_dl = os.environ.get("INSTATERMINAL_DOWNLOADS")
    if custom_dl:
        dl = Path(custom_dl)
        dl.mkdir(parents=True, exist_ok=True)
        return dl

    if is_termux() and not os.environ.get("INSTATERMINAL_HOME"):
        android_candidates = [
            Path.home() / "storage" / "downloads",
            Path("/sdcard/Download"),
            Path("/storage/emulated/0/Download"),
        ]
        for parent in android_candidates:
            try:
                if parent.exists() and os.access(parent, os.W_OK):
                    target = parent / "InstaTerminal"
                    target.mkdir(parents=True, exist_ok=True)
                    return target
            except Exception:
                continue

    downloads = get_app_dir() / "downloads"
    downloads.mkdir(parents=True, exist_ok=True)
    return downloads


def sanitize_folder_name(raw: str, fallback: str = "item") -> str:
    """Sanitize a string so it can be safely used as a folder or file name on Windows/Linux/Android."""
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", (raw or "").strip())
    cleaned = re.sub(r"\s+", "_", cleaned).strip("._ ")
    return cleaned[:48] or fallback


def get_user_download_dir(username: str) -> Path:
    """
    Return the dedicated profile folder for a user under downloads:
    <downloads_dir>/@<username>/
    """
    clean_u = (username or "").strip().lstrip("@").strip("/")
    clean_u = sanitize_folder_name(clean_u, fallback="instagram")
    user_dir = get_downloads_dir() / f"@{clean_u}"
    user_dir.mkdir(parents=True, exist_ok=True)
    return user_dir


def get_user_category_dir(
    username: str,
    category: str,
    subfolder: str = "",
) -> Path:
    """
    Return a categorized folder inside the user's dedicated profile directory:
    <downloads_dir>/@<username>/<category>/[<subfolder>/]

    Standard categories:
    - avatar      (Full HD profile avatar)
    - story       (Active 24-hour stories)
    - highlight   (Story Highlights, optionally with a subfolder per highlight)
    - posts       (Timeline photo posts and carousel albums)
    - reels       (Reels and video posts)
    - followers   (Followers & following lists in .txt and .json)
    - info        (Profile biography and metadata in .txt and .json)
    """
    cat_clean = sanitize_folder_name(category, fallback="media").lower()
    target = get_user_download_dir(username) / cat_clean
    if subfolder:
        target = target / sanitize_folder_name(subfolder, fallback="item")
    target.mkdir(parents=True, exist_ok=True)
    return target


def notify_android_media_scanner(file_path: Path) -> None:
    """Notify Android's MediaScanner on Termux so saved photos/videos appear in the phone Gallery immediately."""
    if not is_termux() or not file_path or not file_path.exists():
        return
    ext = file_path.suffix.lower()
    if ext not in (".jpg", ".jpeg", ".png", ".webp", ".mp4", ".mov", ".mp3"):
        return
    try:
        if shutil.which("termux-media-scan"):
            subprocess.Popen(
                ["termux-media-scan", str(file_path)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        elif shutil.which("am"):
            subprocess.Popen(
                [
                    "am",
                    "broadcast",
                    "-a",
                    "android.intent.action.MEDIA_SCANNER_SCAN_FILE",
                    "-d",
                    f"file://{file_path.resolve()}",
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
    except Exception:
        pass
