"""100% Real Instagram Client Service for InstaTerminal (Zero Mock Data)."""

from __future__ import annotations

import hashlib
import html
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.parse
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import httpx

from instaterminal.core.config import (
    get_cache_dir,
    get_downloads_dir,
    get_session_file,
    get_user_category_dir,
    get_user_download_dir,
    is_termux,
    notify_android_media_scanner,
)
from instaterminal.core.models import (
    HighlightItem,
    PostItem,
    StoryItem,
    UserProfile,
    UserShort,
)


class InstaAuthError(Exception):
    """Raised when Instagram authentication or profile lookup fails."""

    def __init__(self, message: str, requires_2fa: bool = False):
        super().__init__(message)
        self.requires_2fa = requires_2fa


class InstaClientService:
    """Real Instagram service fetching live profile, highlights, and posts directly from Instagram."""

    DEFAULT_USERNAME = ""
    DEFAULT_PASSWORD = ""

    BROWSER_HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Sec-Fetch-Mode": "navigate",
    }

    def __init__(self) -> None:
        self.username: str = ""
        self.authenticated: bool = False
        self._cl = None
        self._profiles_cache: dict[str, UserProfile] = {}
        self._two_factor_identifier: str = ""
        self._pending_cookies: dict[str, str] = {}

    def _ensure_instagrapi(self):
        if self._cl is None:
            from instagrapi import Client

            self._cl = Client()
            self._cl.request_timeout = 15
        return self._cl

    def _has_live_token(self) -> bool:
        if self._cl is None:
            return False
        auth_data = getattr(self._cl, "authorization_data", None) or {}
        uid = getattr(self._cl, "user_id", None)
        return bool(uid and auth_data.get("sessionid"))

    def has_saved_session(self) -> bool:
        session_file = get_session_file()
        return session_file.exists() and session_file.stat().st_size > 10

    def logout(self) -> None:
        """Delete saved session from disk and reset client authentication state."""
        session_file = get_session_file()
        if session_file.exists():
            try:
                session_file.unlink()
            except Exception:
                pass
        self.username = ""
        self.authenticated = False
        self._cl = None

    def login(
        self,
        username: str = "",
        password: str = "",
        verification_code: str = "",
        sessionid: str = "",
    ) -> bool:
        """
        Authenticate with Instagram and persist the session to ~/.instaterminal/session.json
        so subsequent runs never ask for login/password again.
        """
        clean_user = self.normalize_username(username)
        clean_sid = urllib.parse.unquote(sessionid.strip()) if sessionid else ""

        # 1. Direct login via sessionid cookie if provided
        if clean_sid and len(clean_sid) > 10:
            try:
                cl = self._ensure_instagrapi()
                cl.login_by_sessionid(clean_sid)
                info = cl.user_info_v1(int(cl.user_id))
                resolved_user = str(getattr(info, "username", "") or clean_user or "instagram")
                settings = cl.get_settings()
                settings["username"] = resolved_user
                if password:
                    settings["password"] = password
                settings["pre_authenticated"] = True
                settings["trusted_web_cookies"] = {"sessionid": clean_sid, "ds_user_id": str(cl.user_id)}
                get_session_file().write_text(
                    json.dumps(settings, indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )
                self.username = resolved_user
                self.authenticated = True
                return True
            except Exception as exc:
                raise InstaAuthError(f"SessionID orqali kirishda xatolik: {exc}") from exc

        if not clean_user or not password:
            raise InstaAuthError("Instagram username va parol kiritilishi shart.")

        # 2. Authenticate via Instagram Web Ajax Login (works on Desktop & Android Termux without app-version errors)
        if self._auto_relogin_web_ajax(
            clean_user,
            password,
            trusted_cookies=self._pending_cookies or None,
            verification_code=verification_code.strip(),
            raise_on_error=True,
        ):
            return True

        # 3. Fallback to instagrapi mobile login
        try:
            cl = self._ensure_instagrapi()
            cl.login(clean_user, password, verification_code=verification_code.strip())
            settings = cl.get_settings()
            settings["username"] = clean_user
            settings["password"] = password
            settings["pre_authenticated"] = True
            get_session_file().write_text(
                json.dumps(settings, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            self.username = clean_user
            self.authenticated = True
            return True
        except Exception as exc:
            msg = str(exc)
            if "Two-factor" in msg or "two_factor" in msg.lower() or "2fa" in msg.lower():
                raise InstaAuthError(
                    "Ikki bosqichli himoya (2FA) yoqilgan. 6 xonali tasdiqlash kodini kiriting.",
                    requires_2fa=True,
                ) from exc
            raise InstaAuthError(f"Instagramga kirishda xatolik: {msg}") from exc

    def _try_import_browser_session(self, clean_user: str = "", saved_password: str = "") -> bool:
        """Attempt to restore saved session, import active browser sessionid, or refresh via Web Ajax login."""
        cookies: dict[str, str] = {}
        session_file = get_session_file()
        home_session_file = Path.home() / ".instaterminal" / "session.json"
        for cand_file in (session_file, home_session_file):
            if cand_file.exists():
                try:
                    saved_raw = json.loads(cand_file.read_text(encoding="utf-8"))
                    if not clean_user and saved_raw.get("username"):
                        clean_user = self.normalize_username(str(saved_raw["username"]))
                    if not saved_password and saved_raw.get("password"):
                        saved_password = str(saved_raw["password"])
                    saved_trusted = saved_raw.get("trusted_web_cookies") or {}
                    if isinstance(saved_trusted, dict):
                        for k, v in saved_trusted.items():
                            cookies.setdefault(str(k), str(v))
                    saved_auth = saved_raw.get("authorization_data") or {}
                    if isinstance(saved_auth, dict) and saved_auth.get("sessionid"):
                        cookies["sessionid"] = str(saved_auth["sessionid"])
                except Exception:
                    pass

        if not cookies.get("sessionid"):
            try:
                import browser_cookie3  # type: ignore[import-untyped]

                loaders = [
                    getattr(browser_cookie3, "firefox", None),
                    getattr(browser_cookie3, "chrome", None),
                    getattr(browser_cookie3, "edge", None),
                    getattr(browser_cookie3, "brave", None),
                ]
                for loader in loaders:
                    if loader is None:
                        continue
                    try:
                        cj = loader(domain_name="instagram.com")
                        found = {c.name: c.value for c in cj if "instagram.com" in c.domain}
                        if found:
                            cookies.update(found)
                            break
                    except Exception:
                        continue
            except Exception:
                pass

        # 1. Try existing sessionid if valid on v1 API
        sid = cookies.get("sessionid")
        if sid and len(sid) > 10:
            try:
                cl = self._ensure_instagrapi()
                cl.login_by_sessionid(sid)
                info = cl.user_info_v1(int(cl.user_id))
                resolved_user = str(getattr(info, "username", "") or clean_user or "instagram")
                settings = cl.get_settings()
                settings["username"] = resolved_user
                if saved_password:
                    settings["password"] = saved_password
                settings["pre_authenticated"] = True
                settings["trusted_web_cookies"] = cookies
                session_file.write_text(
                    json.dumps(settings, indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )
                self.username = resolved_user
                self.authenticated = True
                return True
            except Exception:
                pass

        # 2. Auto-relogin via Instagram Web Ajax if we have saved username + password
        if clean_user and saved_password:
            return self._auto_relogin_web_ajax(clean_user, saved_password, cookies)
        return False

    def _auto_relogin_web_ajax(
        self,
        username: str,
        password: str,
        trusted_cookies: Optional[dict[str, str]] = None,
        verification_code: str = "",
        raise_on_error: bool = False,
    ) -> bool:
        """Mint a fresh sessionid using Instagram Web Ajax Login and persist it to session.json."""
        cookies = dict(trusted_cookies or {})
        cookies.pop("sessionid", None)
        csrf = cookies.get("csrftoken") or ""
        try:
            with httpx.Client(
                follow_redirects=True,
                timeout=20.0,
                cookies=cookies,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:132.0) Gecko/20100101 Firefox/132.0",
                    "Accept": "*/*",
                    "Accept-Language": "en-US,en;q=0.5",
                },
            ) as client:
                if not csrf:
                    r0 = client.get("https://www.instagram.com/")
                    csrf = client.cookies.get("csrftoken") or ""
                    if not csrf:
                        m = re.search(r'"csrf_token":"([^"]+)"', r0.text)
                        if m:
                            csrf = m.group(1)

                ajax_headers = {
                    "X-CSRFToken": csrf,
                    "X-IG-App-ID": "936619743392459",
                    "X-Instagram-AJAX": "1018000000",
                    "X-Requested-With": "XMLHttpRequest",
                    "Referer": "https://www.instagram.com/",
                }

                if verification_code and self._two_factor_identifier:
                    r1 = client.post(
                        "https://www.instagram.com/api/v1/web/accounts/login/ajax/two_factor/",
                        data={
                            "username": username,
                            "verificationCode": verification_code,
                            "identifier": self._two_factor_identifier,
                            "queryParams": "{}",
                        },
                        headers=ajax_headers,
                    )
                else:
                    ts = int(time.time())
                    data = {
                        "enc_password": f"#PWD_INSTAGRAM_BROWSER:0:{ts}:{password}",
                        "username": username,
                        "queryParams": "{}",
                        "optIntoOneTap": "false",
                        "trustedDeviceRecords": "{}",
                    }
                    r1 = client.post(
                        "https://www.instagram.com/api/v1/web/accounts/login/ajax/",
                        data=data,
                        headers=ajax_headers,
                    )

                resp_json: dict[str, Any] = {}
                try:
                    resp_json = r1.json()
                except Exception:
                    pass

                if resp_json.get("two_factor_required"):
                    tf_info = resp_json.get("two_factor_info") or {}
                    self._two_factor_identifier = str(tf_info.get("two_factor_identifier") or "")
                    self._pending_cookies = dict(client.cookies)
                    if raise_on_error:
                        raise InstaAuthError(
                            "Ikki bosqichli himoya (2FA) kodi talab qilinadi.",
                            requires_2fa=True,
                        )
                    return False

                new_sid = client.cookies.get("sessionid")
                if r1.status_code == 200 and new_sid:
                    cookies.update(dict(client.cookies))
                    cookies["sessionid"] = new_sid
                    cl = self._ensure_instagrapi()
                    cl.login_by_sessionid(new_sid)
                    settings = cl.get_settings()
                    settings["username"] = username
                    settings["password"] = password
                    settings["pre_authenticated"] = True
                    settings["trusted_web_cookies"] = cookies
                    settings["cookies"].update(cookies)
                    get_session_file().write_text(
                        json.dumps(settings, indent=2, ensure_ascii=False),
                        encoding="utf-8",
                    )
                    self.username = username
                    self.authenticated = True
                    self._two_factor_identifier = ""
                    return True

                if raise_on_error and resp_json.get("authenticated") is False:
                    if resp_json.get("user") is False:
                        raise InstaAuthError(f"@{username} nomli Instagram foydalanuvchisi topilmadi.")
                    raise InstaAuthError("Instagram login yoki parol noto'g'ri.")
                if raise_on_error and resp_json.get("message"):
                    raise InstaAuthError(f"Instagram javobi: {resp_json.get('message')}")
        except InstaAuthError:
            raise
        except Exception:
            pass
        return False

    def ensure_default_session(
        self,
        username: str = "",
        password: str = "",
    ) -> bool:
        """Restore saved session from ~/.instaterminal/session.json if available."""
        clean_user = self.normalize_username(username)

        if self.has_saved_session():
            self.load_saved_session()
            if self._has_live_token():
                return True

        return self._try_import_browser_session(clean_user, password)

    def load_saved_session(self) -> bool:
        """Restore saved session configuration from ~/.instaterminal/session.json."""
        session_file = get_session_file()
        if not self.has_saved_session():
            return False
        try:
            raw_data = json.loads(session_file.read_text(encoding="utf-8"))
        except Exception:
            raw_data = {}

        saved_user = self.normalize_username(str(raw_data.get("username") or ""))
        try:
            cl = self._ensure_instagrapi()
            cl.load_settings(session_file)
            if saved_user:
                cl.username = saved_user
        except Exception:
            pass

        if saved_user:
            self.username = saved_user
        self.authenticated = self._has_live_token()
        return self.authenticated

    @staticmethod
    def normalize_username(raw: str) -> str:
        """Extract clean Instagram username from @handle or full URL."""
        clean = raw.strip()
        if "instagram.com/" in clean:
            clean = clean.split("instagram.com/")[-1].split("/")[0].split("?")[0]
        return clean.strip().lstrip("@").strip("/")

    def _fetch_cdn_bytes(self, url: Optional[str], timeout: float = 20.0) -> Optional[bytes]:
        """
        Fetch media bytes from an Instagram CDN URL, automatically falling back to
        scontent.cdninstagram.com if a regional *.fna.fbcdn.net host fails DNS lookup.
        """
        if not url:
            return None
        url_str = str(url).replace("\\/", "/").strip()
        alt_scontent = re.sub(
            r"^https://[^/]+/",
            "https://scontent.cdninstagram.com/",
            url_str,
        )
        alt_fna1 = re.sub(
            r"^https://[^/]+/",
            "https://instagram.ftas1-1.fna.fbcdn.net/",
            url_str,
        )

        # Prefer global scontent.cdninstagram.com when regional ftas2-2 is in URL
        if "ftas2-2.fna.fbcdn.net" in url_str:
            candidates = [alt_scontent, alt_fna1, url_str]
        else:
            candidates = [url_str, alt_scontent, alt_fna1]

        seen: set[str] = set()
        with httpx.Client(
            timeout=timeout,
            follow_redirects=True,
            headers={"User-Agent": self.BROWSER_HEADERS["User-Agent"]},
        ) as client:
            for cand in candidates:
                if not cand or cand in seen:
                    continue
                seen.add(cand)
                try:
                    resp = client.get(cand)
                    if resp.status_code == 200 and resp.content:
                        return resp.content
                except Exception:
                    continue
        return None

    def _download_url_to_cache(self, url: Optional[str], prefix: str = "media") -> Optional[Path]:
        """Download a real Instagram CDN image URL into the local cache directory."""
        if not url:
            return None
        url_str = str(url).replace("\\/", "/")
        digest = hashlib.md5(url_str.encode("utf-8")).hexdigest()[:14]
        dest = get_cache_dir() / f"{prefix}_{digest}.jpg"
        if dest.exists() and dest.stat().st_size > 0:
            return dest
        content = self._fetch_cdn_bytes(url_str, timeout=15.0)
        if content:
            dest.write_bytes(content)
            return dest
        return None

    def _fetch_real_profile_v1(
        self,
        clean_user: str,
        download_media: bool = True,
    ) -> UserProfile:
        """
        Fetch 100% real, complete Instagram profile, active stories, highlights, and
        posts/reels/albums using the authenticated Instagram Mobile v1 API.
        """
        cl = self._ensure_instagrapi()
        u = cl.user_info_by_username_v1(clean_user)

        real_username = str(u.username or clean_user)
        full_name = str(u.full_name or "")
        user_id = str(u.pk or "")
        fbid = str(getattr(u, "interop_messaging_user_fbid", "") or "")
        biography = str(u.biography or "")
        follower_count = int(u.follower_count or 0)
        following_count = int(u.following_count or 0)
        media_count = int(u.media_count or 0)
        is_private = bool(u.is_private)
        is_verified = bool(u.is_verified)
        show_text_post_app_badge = bool(getattr(u, "show_text_post_app_badge", False))
        text_post_app_badge_label = str(getattr(u, "text_post_app_badge_label", "") or "")
        category_name = str(getattr(u, "category_name", "") or getattr(u, "category", "") or "")
        public_email = str(getattr(u, "public_email", "") or "")
        contact_phone = str(getattr(u, "contact_phone_number", "") or getattr(u, "public_phone_number", "") or "")

        bio_links: list[str] = []
        for bl in getattr(u, "bio_links", None) or []:
            if isinstance(bl, dict):
                url_val = str(bl.get("url") or bl.get("lynx_url") or "").strip()
                title_val = str(bl.get("title") or "").strip()
                if url_val:
                    bio_links.append(f"{title_val} ({url_val})" if title_val else url_val)
            else:
                url_val = str(getattr(bl, "url", "") or getattr(bl, "lynx_url", "") or "").strip()
                title_val = str(getattr(bl, "title", "") or "").strip()
                if url_val:
                    bio_links.append(f"{title_val} ({url_val})" if title_val else url_val)

        ext_url = str(u.external_url) if getattr(u, "external_url", None) else (bio_links[0] if bio_links else None)
        if ext_url and not bio_links:
            bio_links.append(ext_url)

        pic_hd = getattr(u, "profile_pic_url_hd", None)
        pic_std = getattr(u, "profile_pic_url", None)
        profile_pic_url = str(pic_hd or pic_std or "").strip() or None

        local_avatar = (
            self._download_url_to_cache(profile_pic_url, prefix=f"avatar_{real_username}")
            if (download_media and profile_pic_url)
            else None
        )

        # 1. Fetch all real Highlights via v1 API
        highlights: list[HighlightItem] = []
        try:
            raw_hls = cl.user_highlights_v1(user_id)
            for h in raw_hls or []:
                hl_id = str(getattr(h, "pk", "") or "").replace("highlight:", "")
                hl_title = str(getattr(h, "title", "") or "Highlight")
                hl_mcount = int(getattr(h, "media_count", 0) or 0)
                hl_pinned = bool(getattr(h, "is_pinned_highlight", False))
                hl_latest = int(getattr(h, "latest_reel_media", 0) or 0)
                created_dt = getattr(h, "created_at", None)
                created_str = (
                    created_dt.strftime("%Y-%m-%d")
                    if isinstance(created_dt, datetime)
                    else str(created_dt or "")
                )
                cov_media = getattr(h, "cover_media", None) or {}
                cov_url = None
                if isinstance(cov_media, dict):
                    cropped = cov_media.get("cropped_image_version") or {}
                    if isinstance(cropped, dict):
                        cov_url = str(cropped.get("url") or "") or None
                highlights.append(
                    HighlightItem(
                        id=hl_id,
                        title=hl_title,
                        owner_username=real_username,
                        cover_url=cov_url,
                        latest_reel_media=hl_latest,
                        media_count=hl_mcount,
                        created_at=created_str,
                        is_pinned=hl_pinned,
                    )
                )
        except Exception:
            pass

        # 2. Fetch active 24h Stories via v1 API
        active_stories: list[StoryItem] = []
        latest_reel_media = 0
        try:
            raw_stories = cl.user_stories_v1(user_id)
            for st in raw_stories or []:
                spk = str(getattr(st, "pk", "") or "")
                scode = str(getattr(st, "code", "") or spk)
                vid_url = str(st.video_url) if getattr(st, "video_url", None) else None
                img_url = str(st.thumbnail_url) if getattr(st, "thumbnail_url", None) else None
                mtype = "video" if (getattr(st, "media_type", 1) == 2 or vid_url) else "photo"
                taken = getattr(st, "taken_at", None)
                if isinstance(taken, datetime):
                    taken_str = taken.strftime("%Y-%m-%d %H:%M:%S")
                    ts_int = int(taken.timestamp())
                    if ts_int > latest_reel_media:
                        latest_reel_media = ts_int
                else:
                    taken_str = str(taken or "Noma'lum")
                local_st_img = (
                    self._download_url_to_cache(img_url, prefix=f"story_{spk}")
                    if (download_media and img_url)
                    else None
                )
                active_stories.append(
                    StoryItem(
                        id=spk,
                        code=scode,
                        username=real_username,
                        full_name=full_name or real_username,
                        taken_at=taken_str,
                        media_type=mtype,
                        video_duration=float(getattr(st, "video_duration", 0.0) or 0.0),
                        image_url=img_url,
                        video_url=vid_url,
                        local_image_path=local_st_img,
                    )
                )
        except Exception:
            pass

        # 3. Fetch real Posts, Carousels, and Reels via v1 API
        final_posts: list[PostItem] = []
        has_any_clips = False
        if media_count > 0:
            try:
                raw_medias = cl.user_medias_v1(user_id, amount=20)
                for m in raw_medias or []:
                    mpk = str(getattr(m, "pk", "") or "")
                    mcode = str(getattr(m, "code", "") or mpk)
                    raw_mtype = int(getattr(m, "media_type", 1) or 1)
                    prod_type = str(getattr(m, "product_type", "") or "feed")
                    if prod_type == "clips":
                        has_any_clips = True
                    if raw_mtype == 8:
                        mtype = "carousel"
                    elif raw_mtype == 2 or getattr(m, "video_url", None):
                        mtype = "video"
                    else:
                        mtype = "photo"

                    taken = getattr(m, "taken_at", None)
                    if isinstance(taken, datetime):
                        created_str = taken.strftime("%Y-%m-%d %H:%M:%S")
                        ts_val = int(taken.timestamp())
                    else:
                        created_str = str(taken or "Noma'lum")
                        ts_val = 0

                    img_url = str(m.thumbnail_url) if getattr(m, "thumbnail_url", None) else None
                    vid_url = str(m.video_url) if getattr(m, "video_url", None) else None

                    res_list: list[dict[str, Any]] = []
                    for r in getattr(m, "resources", None) or []:
                        r_img = str(r.thumbnail_url) if getattr(r, "thumbnail_url", None) else None
                        r_vid = str(r.video_url) if getattr(r, "video_url", None) else None
                        r_pk = str(getattr(r, "pk", "") or "")
                        r_mtype = "video" if (getattr(r, "media_type", 1) == 2 or r_vid) else "photo"
                        res_list.append(
                            {
                                "pk": r_pk,
                                "media_type": r_mtype,
                                "image_url": r_img,
                                "video_url": r_vid,
                            }
                        )
                    if not img_url and res_list:
                        img_url = res_list[0].get("image_url")

                    local_img = (
                        self._download_url_to_cache(img_url, prefix=f"post_{mcode}")
                        if (download_media and img_url)
                        else None
                    )

                    loc_obj = getattr(m, "location", None)
                    loc_name = str(getattr(loc_obj, "name", "") or "") if loc_obj else None

                    play_cnt = int(
                        getattr(m, "play_count", 0)
                        or getattr(m, "view_count", 0)
                        or 0
                    )

                    final_posts.append(
                        PostItem(
                            id=mpk,
                            code=mcode,
                            username=real_username,
                            full_name=full_name or real_username,
                            caption=str(getattr(m, "caption_text", "") or ""),
                            like_count=int(getattr(m, "like_count", 0) or 0),
                            comment_count=int(getattr(m, "comment_count", 0) or 0),
                            likes_hidden=bool(getattr(m, "like_and_view_counts_disabled", False)),
                            created_at=created_str,
                            timestamp=ts_val,
                            media_type=mtype,
                            typename=prod_type,
                            product_type=prod_type,
                            image_url=img_url,
                            video_url=vid_url,
                            local_image_path=local_img,
                            play_count=play_cnt,
                            resources=res_list,
                            location=loc_name or None,
                        )
                    )
            except Exception:
                pass

        user_dump: dict[str, Any] = {}
        try:
            user_dump = (
                u.model_dump(mode="json")
                if hasattr(u, "model_dump")
                else u.dict()
            )
        except Exception:
            user_dump = {"pk": user_id, "username": real_username}

        profile = UserProfile(
            user_id=user_id,
            fbid=fbid,
            username=real_username,
            full_name=full_name,
            biography=biography,
            follower_count=follower_count,
            following_count=following_count,
            media_count=media_count,
            is_private=is_private,
            is_verified=is_verified,
            has_public_story=len(active_stories) > 0,
            has_any_clips=has_any_clips,
            latest_reel_media=latest_reel_media,
            show_text_post_app_badge=show_text_post_app_badge,
            text_post_app_badge_label=text_post_app_badge_label,
            bio_links=bio_links,
            external_url=ext_url,
            profile_pic_url=profile_pic_url,
            local_avatar_path=local_avatar,
            profile_link=f"https://www.instagram.com/{real_username}/",
            category_name=category_name,
            public_email=public_email,
            contact_phone_number=contact_phone,
            stories=active_stories,
            highlights=highlights,
            posts=final_posts,
            raw_data={
                "source": "instagram_mobile_api_v1",
                "user": user_dump,
                "highlights_count": len(highlights),
                "active_stories_count": len(active_stories),
                "posts_fetched": len(final_posts),
            },
        )
        self._profiles_cache[real_username.lower()] = profile
        return profile

    def fetch_real_profile(
        self,
        username: str,
        download_media: bool = True,
    ) -> UserProfile:
        """
        Fetch 100% real Instagram profile, statistics, bio, links, story highlights,
        active stories, and timeline posts directly from Instagram servers (no mock data).
        """
        clean_user = self.normalize_username(username)
        if not clean_user:
            raise ValueError("Instagram username kiritilishi shart.")

        if not self._has_live_token():
            self.ensure_default_session()

        if self._has_live_token():
            try:
                return self._fetch_real_profile_v1(
                    clean_user,
                    download_media=download_media,
                )
            except Exception as exc:
                err_name = type(exc).__name__.lower()
                if "usernotfound" in err_name or "not found" in str(exc).lower():
                    raise ValueError(
                        f"@{clean_user} profili Instagramda topilmadi yoki o'chirilgan."
                    ) from exc
                # Try refreshing browser session if token expired
                if self._try_import_browser_session(self.username or self.DEFAULT_USERNAME):
                    try:
                        return self._fetch_real_profile_v1(
                            clean_user,
                            download_media=download_media,
                        )
                    except Exception:
                        pass

        url_main = f"https://www.instagram.com/{clean_user}/"
        url_embed = f"https://www.instagram.com/{clean_user}/embed/"

        cookies: dict[str, str] = {}
        if self._cl is not None:
            auth_data = getattr(self._cl, "authorization_data", None) or {}
            sid = auth_data.get("sessionid")
            if sid:
                cookies["sessionid"] = str(sid)

        with httpx.Client(
            follow_redirects=True,
            timeout=20.0,
            headers=self.BROWSER_HEADERS,
            cookies=cookies,
        ) as client:
            r_main = client.get(url_main)
            r_embed = client.get(url_embed)

        # 1. Extract Polaris RelayPrefetchedStreamCache data from main profile HTML
        xig_user: dict[str, Any] = {}
        polaris_edges: list[dict[str, Any]] = []

        for script_body in re.findall(r"<script[^>]*>(.*?)</script>", r_main.text, re.S):
            if "xig_user_by_username" not in script_body:
                continue
            try:
                payload = json.loads(script_body)

                def _walk(obj: Any) -> None:
                    if isinstance(obj, dict):
                        u = obj.get("xig_user_by_username")
                        if isinstance(u, dict):
                            if "polaris_ordered_timeline_connection" in u:
                                conn = u.get("polaris_ordered_timeline_connection") or {}
                                edges = conn.get("edges") or []
                                polaris_edges.extend(edges)
                            else:
                                xig_user.update(u)
                        for v in obj.values():
                            _walk(v)
                    elif isinstance(obj, list):
                        for item in obj:
                            _walk(item)

                _walk(payload)
            except Exception:
                pass

        # 2. Extract contextJSON from /embed/ endpoint
        embed_ctx: dict[str, Any] = {}
        m_ctx = re.search(r'"contextJSON":("(?:\\.|[^"\\])*")', r_embed.text)
        if not m_ctx:
            m_ctx = re.search(
                r'"contextJSON"\s*,\s*\[\]\s*,\s*\[("(?:\\.|[^"\\])*")\]',
                r_embed.text,
            )
        if m_ctx:
            try:
                raw_json = json.loads(m_ctx.group(1))
                parsed = json.loads(raw_json)
                embed_ctx = parsed.get("context") or parsed
            except Exception:
                pass

        # 3. Extract fallback OpenGraph meta tags if needed
        og_title_m = re.search(r'property="og:title"\s+content="(.*?)"', r_main.text)
        og_desc_m = re.search(r'property="og:description"\s+content="(.*?)"', r_main.text)
        og_img_m = re.search(r'property="og:image"\s+content="(.*?)"', r_main.text)

        if not xig_user and not embed_ctx.get("username") and not embed_ctx.get("owner_id"):
            og_title_val = html.unescape(og_title_m.group(1)).strip() if og_title_m else ""
            if not og_title_val or og_title_val.lower() == "instagram":
                raise ValueError(
                    f"@{clean_user} profili Instagramda topilmadi yoki o'chirilgan."
                )

        real_username = str(
            xig_user.get("username") or embed_ctx.get("username") or clean_user
        )
        full_name = str(
            xig_user.get("full_name") or embed_ctx.get("full_name") or ""
        )
        user_id = str(
            xig_user.get("pk") or embed_ctx.get("owner_id") or ""
        )
        fbid = str(xig_user.get("id") or "")
        biography = str(xig_user.get("biography") or "")

        follower_count = int(
            xig_user.get("follower_count")
            if xig_user.get("follower_count") is not None
            else (embed_ctx.get("followers_count") or 0)
        )
        following_count = int(
            xig_user.get("following_count")
            if xig_user.get("following_count") is not None
            else 0
        )

        # Total media count from embed_ctx or xig_user or og_description
        posts_count_val = embed_ctx.get("posts_count")
        if posts_count_val is None:
            posts_count_val = xig_user.get("all_media_count")
        if posts_count_val is None and og_desc_m:
            desc_text = html.unescape(og_desc_m.group(1))
            m_posts = re.search(r"([\d,.]+[KMB]?)\s+Posts", desc_text, re.I)
            if m_posts:
                raw_num = m_posts.group(1).replace(",", "")
                if raw_num.isdigit():
                    posts_count_val = int(raw_num)
        media_count = int(posts_count_val or 0)

        is_private = bool(xig_user.get("is_private", False))
        is_verified = bool(
            xig_user.get("is_verified") or embed_ctx.get("is_verified") or embed_ctx.get("verified")
        )
        is_memorialized = bool(xig_user.get("is_memorialized", False))
        is_unpublished = bool(xig_user.get("is_unpublished", False))
        is_coppa_enforced = bool(xig_user.get("is_coppa_enforced", False))
        has_public_story = bool(embed_ctx.get("has_public_story", False))
        has_any_clips = bool(xig_user.get("has_any_clips", False))
        latest_reel_media = int(xig_user.get("latest_reel_media") or 0)
        show_text_post_app_badge = bool(xig_user.get("show_text_post_app_badge", False))
        text_post_app_badge_label = str(xig_user.get("text_post_app_badge_label") or "")

        pronouns_raw = xig_user.get("pronouns") or embed_ctx.get("pronouns") or []
        pronouns = [str(p) for p in pronouns_raw if p]

        bio_links_raw = xig_user.get("bio_links") or []
        bio_links: list[str] = []
        for bl in bio_links_raw:
            if isinstance(bl, dict):
                url_val = str(bl.get("url") or bl.get("lynx_url") or "").strip()
                title_val = str(bl.get("title") or "").strip()
                if url_val:
                    bio_links.append(f"{title_val} ({url_val})" if title_val else url_val)
            elif isinstance(bl, str) and bl.strip():
                bio_links.append(bl.strip())

        account_badges = [str(b) for b in (xig_user.get("account_badges") or []) if b]

        profile_pic_url = str(
            xig_user.get("profile_pic_url")
            or embed_ctx.get("profile_pic_url")
            or (html.unescape(og_img_m.group(1)) if og_img_m else "")
        ).strip() or None

        local_avatar = (
            self._download_url_to_cache(profile_pic_url, prefix=f"avatar_{real_username}")
            if (download_media and profile_pic_url)
            else None
        )

        # 4. Extract Story Highlights
        highlights: list[HighlightItem] = []
        hl_conn = xig_user.get("lox_highlights_connection") or {}
        for edge in hl_conn.get("edges") or []:
            node = edge.get("node") or {}
            hl_id = str(node.get("id") or "")
            hl_title = str(node.get("title") or "Highlight")
            hl_cover = str(node.get("cover_media_cropped_thumbnail_url") or "") or None
            if hl_id or hl_title:
                highlights.append(
                    HighlightItem(
                        id=hl_id,
                        title=hl_title,
                        owner_username=str(node.get("owner_username") or real_username),
                        cover_url=hl_cover,
                    )
                )

        # 5. Extract and merge real Posts from embed graphql_media + Polaris timeline edges
        posts_by_code: dict[str, PostItem] = {}
        ordered_codes: list[str] = []

        for gm in embed_ctx.get("graphql_media") or []:
            sm = gm.get("shortcode_media") or {}
            code = str(sm.get("shortcode") or "").strip()
            if not code:
                continue
            pk = str(sm.get("id") or code)
            typename = str(sm.get("__typename") or "")
            is_video = bool(sm.get("is_video", False))
            if "Sidecar" in typename or "Carousel" in typename:
                mtype = "carousel"
            elif is_video or "Video" in typename:
                mtype = "video"
            else:
                mtype = "photo"

            cap_edges = (sm.get("edge_media_to_caption") or {}).get("edges") or []
            caption_text = ""
            if cap_edges and isinstance(cap_edges[0], dict):
                caption_text = str((cap_edges[0].get("node") or {}).get("text") or "")

            likes_obj = sm.get("edge_liked_by") or sm.get("edge_media_preview_like") or {}
            like_count = int(likes_obj.get("count") or 0) if isinstance(likes_obj, dict) else 0
            likes_hidden = bool(sm.get("like_and_view_counts_disabled", False))

            comm_obj = sm.get("edge_media_to_comment") or {}
            comment_count = int(comm_obj.get("count") or 0) if isinstance(comm_obj, dict) else 0
            commenter_count = int(sm.get("commenter_count") or 0)

            ts = int(sm.get("taken_at_timestamp") or 0)
            created_str = (
                datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
                if ts > 0
                else "Noma'lum"
            )

            dims = sm.get("dimensions") or {}
            dim_str = (
                f"{dims.get('width')}x{dims.get('height')}"
                if dims.get("width") and dims.get("height")
                else ""
            )

            loc_obj = sm.get("location")
            loc_name = str(loc_obj.get("name") or "") if isinstance(loc_obj, dict) else None

            coauthors = [
                str(c.get("username") or "")
                for c in (sm.get("coauthor_producers") or [])
                if isinstance(c, dict) and c.get("username")
            ]
            pinned_users = sm.get("pinned_for_users") or []
            is_pinned = len(pinned_users) > 0

            disp_url = str(sm.get("display_url") or "") or None
            local_img = (
                self._download_url_to_cache(disp_url, prefix=f"post_{code}")
                if (download_media and disp_url)
                else None
            )

            post_item = PostItem(
                id=pk,
                code=code,
                username=real_username,
                full_name=full_name or real_username,
                caption=caption_text,
                like_count=like_count,
                comment_count=comment_count,
                commenter_count=commenter_count,
                likes_hidden=likes_hidden,
                created_at=created_str,
                timestamp=ts,
                media_type=mtype,
                typename=typename,
                dimensions=dim_str,
                is_paid_partnership=bool(sm.get("is_paid_partnership", False)),
                is_affiliate=bool(sm.get("is_affiliate", False)),
                is_pinned=is_pinned,
                coauthors=coauthors,
                image_url=disp_url,
                local_image_path=local_img,
                location=loc_name or None,
            )
            posts_by_code[code] = post_item
            ordered_codes.append(code)

        # Merge with Polaris timeline edges (gives up to 12 posts + accessibility_caption + product_type)
        for edge in polaris_edges:
            node = edge.get("node") or {}
            code = str(node.get("code") or "").strip()
            if not code:
                continue
            pk = str(node.get("pk") or code)
            typename = str(node.get("__typename") or "")
            product_type = str(node.get("product_type") or "feed")
            acc_caption = str(node.get("accessibility_caption") or "")
            cap_obj = node.get("caption")
            cap_text = str(cap_obj.get("text") or "") if isinstance(cap_obj, dict) else ""
            disp_uri = str(node.get("display_uri") or "") or None
            raw_mtype = int(node.get("media_type") or 1)
            if raw_mtype == 8 or "Carousel" in typename:
                mtype = "carousel"
            elif raw_mtype == 2 or "Video" in typename:
                mtype = "video"
            else:
                mtype = "photo"

            if code in posts_by_code:
                existing = posts_by_code[code]
                if acc_caption and not existing.accessibility_caption:
                    existing.accessibility_caption = acc_caption
                if product_type:
                    existing.product_type = product_type
                if cap_text and not existing.caption:
                    existing.caption = cap_text
                if disp_uri and not existing.image_url:
                    existing.image_url = disp_uri
                if existing.local_image_path is None and download_media and existing.image_url:
                    existing.local_image_path = self._download_url_to_cache(
                        existing.image_url, prefix=f"post_{code}"
                    )
            else:
                local_img = (
                    self._download_url_to_cache(disp_uri, prefix=f"post_{code}")
                    if (download_media and disp_uri)
                    else None
                )
                created_hint = "Instagram Post"
                if " on " in acc_caption:
                    created_hint = acc_caption.split(" on ")[-1].rstrip(".")
                posts_by_code[code] = PostItem(
                    id=pk,
                    code=code,
                    username=real_username,
                    full_name=full_name or real_username,
                    caption=cap_text,
                    accessibility_caption=acc_caption,
                    like_count=0,
                    comment_count=0,
                    created_at=created_hint,
                    media_type=mtype,
                    typename=typename,
                    product_type=product_type,
                    image_url=disp_uri,
                    local_image_path=local_img,
                )
                ordered_codes.append(code)

        final_posts = [posts_by_code[c] for c in ordered_codes]
        if media_count == 0 and final_posts:
            media_count = len(final_posts)

        profile = UserProfile(
            user_id=user_id,
            fbid=fbid,
            username=real_username,
            full_name=full_name,
            biography=biography,
            follower_count=follower_count,
            following_count=following_count,
            media_count=media_count,
            is_private=is_private,
            is_verified=is_verified,
            is_memorialized=is_memorialized,
            is_unpublished=is_unpublished,
            is_coppa_enforced=is_coppa_enforced,
            has_public_story=has_public_story,
            has_any_clips=has_any_clips,
            latest_reel_media=latest_reel_media,
            show_text_post_app_badge=show_text_post_app_badge,
            text_post_app_badge_label=text_post_app_badge_label,
            pronouns=pronouns,
            bio_links=bio_links,
            account_badges=account_badges,
            external_url=bio_links[0] if bio_links else None,
            profile_pic_url=profile_pic_url,
            local_avatar_path=local_avatar,
            profile_link=f"https://www.instagram.com/{real_username}/",
            request_id=str(embed_ctx.get("request_id") or ""),
            highlights=highlights,
            posts=final_posts,
            raw_data={
                "xig_user_by_username": xig_user,
                "embed_context": {
                    k: v for k, v in embed_ctx.items() if k != "graphql_media"
                },
                "posts_fetched": len(final_posts),
            },
        )
        self._profiles_cache[real_username.lower()] = profile
        return profile

    def get_user_profile(self, username: Optional[str] = None) -> UserProfile:
        """Fetch real UserProfile for given username (or default session user)."""
        target = self.normalize_username(username or self.username or self.DEFAULT_USERNAME)
        return self.fetch_real_profile(target)

    def search_users(self, query: str) -> list[UserProfile]:
        """Search and return real Instagram profile for @query."""
        profile = self.fetch_real_profile(query)
        return [profile]

    def _find_cached_highlight(self, highlight_id: str) -> Optional[HighlightItem]:
        """Look up a HighlightItem across cached profiles by its ID."""
        for prof in self._profiles_cache.values():
            for hl in prof.highlights:
                if hl.id == highlight_id:
                    return hl
        return None

    def fetch_highlight_stories(
        self,
        highlight_id: str,
        download_previews: bool = True,
        fallback_highlight: Optional[HighlightItem] = None,
    ) -> HighlightItem:
        """
        Fetch all real Story items (Full HD photos and MP4 videos) inside an Instagram
        Story Highlight directly from https://www.instagram.com/stories/highlights/{id}/,
        falling back to the profile's lox_highlights_connection cover media when Instagram
        restricts inner story items for unverified accounts.
        """
        clean_id = str(highlight_id).strip().replace("highlight:", "").strip("/")
        if "highlights/" in clean_id:
            clean_id = clean_id.split("highlights/")[-1].split("/")[0].split("?")[0]
        if not clean_id:
            raise ValueError("Highlight ID kiritilishi shart.")

        if fallback_highlight is None:
            fallback_highlight = self._find_cached_highlight(clean_id)

        if not self._has_live_token():
            self.ensure_default_session()

        # 1. Try fetching via authenticated client first (returns 100% full story list, videos and photos)
        if self._has_live_token():
            try:
                cl = self._ensure_instagrapi()
                raw_hl = cl.highlight_info(clean_id)
                if raw_hl and hasattr(raw_hl, "items") and raw_hl.items:
                    items_list: list[StoryItem] = []
                    for it in raw_hl.items:
                        pk = str(it.pk)
                        vid_url = str(it.video_url) if it.video_url else None
                        img_url = str(it.thumbnail_url) if it.thumbnail_url else None
                        mtype = "video" if (it.media_type == 2 or vid_url) else "photo"
                        taken = getattr(it, "taken_at", None)
                        taken_str = (
                            taken.strftime("%Y-%m-%d %H:%M:%S")
                            if isinstance(taken, datetime)
                            else str(taken or "Noma'lum")
                        )
                        local_img = (
                            self._download_url_to_cache(img_url, prefix=f"hl_story_{pk}")
                            if (download_previews and img_url)
                            else None
                        )
                        items_list.append(
                            StoryItem(
                                id=pk,
                                code=str(getattr(it, "code", "") or pk),
                                username=getattr(raw_hl.user, "username", "") or (fallback_highlight.owner_username if fallback_highlight else self.username),
                                full_name=getattr(raw_hl.user, "full_name", "") or "",
                                taken_at=taken_str,
                                media_type=mtype,
                                video_duration=float(getattr(it, "video_duration", 0.0) or 0.0),
                                has_audio=bool(getattr(it, "has_audio", False)),
                                image_url=img_url,
                                video_url=vid_url,
                                local_image_path=local_img,
                                caption=str(getattr(it, "caption_text", "") or ""),
                            )
                        )
                    return HighlightItem(
                        id=clean_id,
                        title=str(getattr(raw_hl, "title", "") or (fallback_highlight.title if fallback_highlight else "Highlight")),
                        owner_username=getattr(raw_hl.user, "username", "") or (fallback_highlight.owner_username if fallback_highlight else ""),
                        cover_url=str(getattr(raw_hl, "cover_media", None) or (fallback_highlight.cover_url if fallback_highlight else "")),
                        items=items_list,
                    )
            except Exception:
                pass

        cookies: dict[str, str] = {}
        if self._cl is not None:
            auth_data = getattr(self._cl, "authorization_data", None) or {}
            sid = auth_data.get("sessionid")
            if sid:
                cookies["sessionid"] = str(sid)

        url = f"https://www.instagram.com/stories/highlights/{clean_id}/"
        with httpx.Client(
            follow_redirects=True,
            timeout=20.0,
            headers=self.BROWSER_HEADERS,
            cookies=cookies,
        ) as client:
            resp = client.get(url)

        hl_node: dict[str, Any] = {}
        for script_body in re.findall(r"<script[^>]*>(.*?)</script>", resp.text, re.S):
            if "xdt_api__v1__feed__reels_media__connection" not in script_body:
                continue
            try:
                payload = json.loads(script_body)

                def _walk(obj: Any) -> None:
                    if isinstance(obj, dict):
                        conn = obj.get("xdt_api__v1__feed__reels_media__connection")
                        if isinstance(conn, dict):
                            edges = conn.get("edges") or []
                            if edges and isinstance(edges[0], dict):
                                node = edges[0].get("node")
                                if isinstance(node, dict):
                                    hl_node.update(node)
                        for v in obj.values():
                            _walk(v)
                    elif isinstance(obj, list):
                        for item in obj:
                            _walk(item)

                _walk(payload)
            except Exception:
                pass

        if not hl_node:
            if fallback_highlight and fallback_highlight.cover_url:
                local_cov = (
                    self._download_url_to_cache(
                        fallback_highlight.cover_url,
                        prefix=f"hl_cover_{clean_id}",
                    )
                    if download_previews
                    else None
                )
                cover_story = StoryItem(
                    id=clean_id,
                    code=f"HL_{clean_id[-6:]}",
                    username=fallback_highlight.owner_username or self.username,
                    full_name=fallback_highlight.owner_username or self.username,
                    taken_at="Highlight Story",
                    media_type="photo",
                    dimensions="Highlight Media",
                    image_url=fallback_highlight.cover_url,
                    local_image_path=local_cov,
                    caption=f"Highlight: {fallback_highlight.title}",
                )
                return HighlightItem(
                    id=clean_id,
                    title=fallback_highlight.title,
                    owner_username=fallback_highlight.owner_username,
                    cover_url=fallback_highlight.cover_url,
                    local_cover_path=local_cov,
                    items=[cover_story],
                )
            raise ValueError(
                f"Highlight ({clean_id}) topilmadi yoki ichida storylar mavjud emas."
            )

        title = str(hl_node.get("title") or "Highlight")
        user_obj = hl_node.get("user") or {}
        owner_username = str(user_obj.get("username") or "")
        owner_fullname = str(user_obj.get("full_name") or owner_username)
        cover_obj = (hl_node.get("cover_media") or {}).get("cropped_image_version") or {}
        cover_url = str(cover_obj.get("url") or "") or None
        local_cover = (
            self._download_url_to_cache(cover_url, prefix=f"hl_cover_{clean_id}")
            if (download_previews and cover_url)
            else None
        )

        story_items: list[StoryItem] = []
        for raw_item in hl_node.get("items") or []:
            if not isinstance(raw_item, dict):
                continue
            pk = str(raw_item.get("pk") or raw_item.get("id") or "")
            code = str(raw_item.get("code") or "")
            raw_mtype = int(raw_item.get("media_type") or 1)
            vids = raw_item.get("video_versions") or []
            imgs = (raw_item.get("image_versions2") or {}).get("candidates") or []

            img_url = str(imgs[0].get("url") or "") if imgs and isinstance(imgs[0], dict) else None
            vid_url = str(vids[0].get("url") or "") if vids and isinstance(vids[0], dict) else None
            media_type = "video" if (raw_mtype == 2 or vid_url) else "photo"

            w = raw_item.get("original_width")
            h = raw_item.get("original_height")
            dim_str = f"{w}x{h}" if (w and h) else ""

            ts = int(raw_item.get("taken_at") or 0)
            taken_str = (
                datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
                if ts > 0
                else "Noma'lum"
            )

            dur = float(raw_item.get("video_duration") or 0.0)
            has_audio = bool(raw_item.get("has_audio", False))
            acc_cap = str(raw_item.get("accessibility_caption") or "")
            cap_obj = raw_item.get("caption")
            cap_text = (
                str(cap_obj.get("text") or "")
                if isinstance(cap_obj, dict)
                else str(cap_obj or "")
            )

            local_img = (
                self._download_url_to_cache(img_url, prefix=f"hl_story_{pk}")
                if (download_previews and img_url)
                else None
            )

            story_items.append(
                StoryItem(
                    id=pk,
                    code=code,
                    username=owner_username,
                    full_name=owner_fullname,
                    taken_at=taken_str,
                    media_type=media_type,
                    dimensions=dim_str,
                    video_duration=dur,
                    has_audio=has_audio,
                    image_url=img_url,
                    video_url=vid_url,
                    local_image_path=local_img,
                    caption=cap_text,
                    accessibility_caption=acc_cap,
                )
            )

        return HighlightItem(
            id=clean_id,
            title=title,
            owner_username=owner_username,
            cover_url=cover_url,
            local_cover_path=local_cover,
            latest_reel_media=int(hl_node.get("latest_reel_media") or 0),
            items=story_items,
        )

    @staticmethod
    def _sanitize_filename(raw: str) -> str:
        cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", raw.strip())
        return cleaned[:48].strip("._ ") or "item"

    def _get_web_cookies(self) -> dict[str, str]:
        cookies: dict[str, str] = {}
        session_file = get_session_file()
        if session_file.exists():
            try:
                raw = json.loads(session_file.read_text(encoding="utf-8"))
                for src in (raw.get("trusted_web_cookies"), raw.get("cookies")):
                    if isinstance(src, dict):
                        for k, v in src.items():
                            if v:
                                cookies[str(k)] = urllib.parse.unquote(str(v))
            except Exception:
                pass
        if self._cl is not None:
            auth_data = getattr(self._cl, "authorization_data", None) or {}
            sid = auth_data.get("sessionid")
            if sid:
                cookies["sessionid"] = urllib.parse.unquote(str(sid))
        return cookies

    def download_story_item(
        self,
        item: StoryItem,
        highlight_id: str = "",
        target_dir: Optional[Path] = None,
        highlight_title: str = "",
        owner_username: str = "",
    ) -> Optional[Path]:
        """
        Download a Story item (Full HD .mp4 video or Full HD .jpg photo)
        into target_dir (or downloads/@<username>/story/ or downloads/@<username>/highlight/<title>_<id>/)
        and return the saved file path.
        """
        uname = self.normalize_username(item.username or owner_username) or "instagram"
        if target_dir is not None:
            downloads_dir = target_dir
        elif highlight_id and highlight_id not in ("active", "active_24h"):
            safe_title = self._sanitize_filename(highlight_title) if highlight_title else ""
            sub = f"{safe_title}_{highlight_id}" if safe_title else str(highlight_id)
            downloads_dir = get_user_category_dir(uname, "highlight", subfolder=sub)
        else:
            downloads_dir = get_user_category_dir(uname, "story")

        downloads_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        hl_tag = f"_hl_{highlight_id}" if highlight_id else ""

        if item.media_type == "video" and item.video_url:
            dest = downloads_dir / f"{uname}{hl_tag}_story_{item.id}_{timestamp}.mp4"
            content = self._fetch_cdn_bytes(item.video_url, timeout=30.0)
            if content:
                dest.write_bytes(content)
                item.local_video_path = dest
                notify_android_media_scanner(dest)
                return dest

        # Photo story (or fallback thumbnail)
        if item.local_image_path and item.local_image_path.exists():
            dest = downloads_dir / f"{uname}{hl_tag}_story_{item.id}_{timestamp}.jpg"
            shutil.copy2(item.local_image_path, dest)
            notify_android_media_scanner(dest)
            return dest

        if item.image_url:
            dest = downloads_dir / f"{uname}{hl_tag}_story_{item.id}_{timestamp}.jpg"
            content = self._fetch_cdn_bytes(item.image_url, timeout=20.0)
            if content:
                dest.write_bytes(content)
                notify_android_media_scanner(dest)
                return dest

        return None

    def download_all_highlight_stories(
        self,
        highlight: HighlightItem,
        target_dir: Optional[Path] = None,
        include_cover: bool = False,
    ) -> list[Path]:
        """Download all story items (and optionally cover image) inside a Highlight into @<username>/highlight/<title>_<id>/."""
        uname = (
            self.normalize_username(highlight.owner_username)
            or (self.normalize_username(highlight.items[0].username) if highlight.items else "")
            or "instagram"
        )
        if target_dir is not None:
            downloads_dir = target_dir
        elif highlight.id in ("active", "active_24h"):
            downloads_dir = get_user_category_dir(uname, "story")
        else:
            safe_title = self._sanitize_filename(highlight.title or "highlight")
            sub = f"{safe_title}_{highlight.id}" if highlight.id else safe_title
            downloads_dir = get_user_category_dir(uname, "highlight", subfolder=sub)

        downloads_dir.mkdir(parents=True, exist_ok=True)
        saved_files: list[Path] = []

        if include_cover and highlight.cover_url:
            cov_file = self.save_media_to_downloads(
                highlight.local_cover_path or highlight.cover_url,
                f"{uname}_hl_{highlight.id}_cover",
                target_dir=downloads_dir,
                username=uname,
                category="highlight",
            )
            if cov_file:
                saved_files.append(cov_file)

        for item in highlight.items:
            saved = self.download_story_item(
                item,
                highlight_id=highlight.id,
                target_dir=downloads_dir,
                highlight_title=highlight.title,
                owner_username=uname,
            )
            if saved:
                saved_files.append(saved)
        return saved_files

    def download_all_stories(
        self,
        stories: list[StoryItem],
        target_dir: Optional[Path] = None,
        username: str = "",
    ) -> list[Path]:
        """Download all active 24h story items to @<username>/story/."""
        uname = (
            self.normalize_username(username)
            or (self.normalize_username(stories[0].username) if stories else "")
            or "instagram"
        )
        downloads_dir = target_dir or get_user_category_dir(uname, "story")
        saved_files: list[Path] = []
        for item in stories:
            saved = self.download_story_item(
                item,
                highlight_id="active",
                target_dir=downloads_dir,
                owner_username=uname,
            )
            if saved:
                saved_files.append(saved)
        return saved_files

    def download_all_post_media(
        self,
        post: PostItem,
        target_dir: Optional[Path] = None,
    ) -> list[Path]:
        """Download all files for a Post, Reel, or Carousel album into @<username>/posts/ or @<username>/reels/."""
        uname = self.normalize_username(post.username) or "instagram"
        is_reel = post.product_type == "clips" or post.media_type == "video"
        default_cat = "reels" if is_reel else "posts"
        downloads_dir = target_dir or get_user_category_dir(uname, default_cat)
        downloads_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        saved_files: list[Path] = []

        if post.media_type == "carousel" and post.resources:
            for idx, res in enumerate(post.resources, start=1):
                r_type = res.get("media_type", "photo")
                r_vid = res.get("video_url")
                r_img = res.get("image_url")
                if r_type == "video" and r_vid:
                    dest = downloads_dir / f"{uname}_{post.code}_slide{idx}_{timestamp}.mp4"
                    content = self._fetch_cdn_bytes(str(r_vid), timeout=30.0)
                    if content:
                        dest.write_bytes(content)
                        notify_android_media_scanner(dest)
                        saved_files.append(dest)
                        continue
                if r_img:
                    dest = downloads_dir / f"{uname}_{post.code}_slide{idx}_{timestamp}.jpg"
                    content = self._fetch_cdn_bytes(str(r_img), timeout=20.0)
                    if content:
                        dest.write_bytes(content)
                        notify_android_media_scanner(dest)
                        saved_files.append(dest)
            if saved_files:
                return saved_files

        single = self.download_post_media(post, target_dir=downloads_dir)
        if single:
            saved_files.append(single)
        return saved_files

    def download_post_media(
        self,
        post: PostItem,
        target_dir: Optional[Path] = None,
    ) -> Optional[Path]:
        """
        Download a Post or Reel (Full HD .mp4 video if video/reel, or Full HD .jpg photo)
        into @<username>/reels/ or @<username>/posts/ and return the saved file path.
        """
        uname = self.normalize_username(post.username) or "instagram"
        is_reel = post.product_type == "clips" or post.media_type == "video"
        default_cat = "reels" if is_reel else "posts"
        downloads_dir = target_dir or get_user_category_dir(uname, default_cat)
        downloads_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        if post.media_type == "video" or post.product_type == "clips":
            vid_url = post.video_url
            if not vid_url and post.code:
                try:
                    with httpx.Client(
                        follow_redirects=True,
                        timeout=15.0,
                        headers=self.BROWSER_HEADERS,
                        cookies=self._get_web_cookies(),
                    ) as client:
                        r = client.get(f"https://www.instagram.com/p/{post.code}/")
                    m_vid = re.search(
                        r'"video_versions"\s*:\s*\[\s*\{[^}]*"url"\s*:\s*"([^"]+)"',
                        r.text,
                    )
                    if m_vid:
                        vid_url = json.loads(f'"{m_vid.group(1)}"')
                        post.video_url = vid_url
                except Exception:
                    pass

            if vid_url:
                dest_mp4 = downloads_dir / f"{uname}_{post.code}_{timestamp}.mp4"
                content = self._fetch_cdn_bytes(vid_url, timeout=30.0)
                if content:
                    dest_mp4.write_bytes(content)
                    notify_android_media_scanner(dest_mp4)
                    return dest_mp4

        return self.save_media_to_downloads(
            post.local_image_path or post.image_url,
            f"{uname}_{post.code}",
            target_dir=downloads_dir,
            username=uname,
            category=default_cat,
        )

    def save_media_to_downloads(
        self,
        path_or_url: Optional[Path | str],
        filename_prefix: str,
        target_dir: Optional[Path] = None,
        username: str = "",
        category: str = "avatar",
    ) -> Optional[Path]:
        """Save a cached media file or URL into target_dir (or @<username>/<category>/)."""
        if not path_or_url:
            return None
        uname = self.normalize_username(username)
        if not uname:
            uname = filename_prefix.split("_avatar")[0].split("_hl_")[0] or "instagram"
        downloads_dir = target_dir or get_user_category_dir(uname, category)
        downloads_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        dest = downloads_dir / f"{filename_prefix}_{timestamp}.jpg"

        if isinstance(path_or_url, Path) and path_or_url.exists():
            shutil.copy2(path_or_url, dest)
            notify_android_media_scanner(dest)
            return dest

        cached = self._download_url_to_cache(str(path_or_url), prefix=filename_prefix)
        if cached and cached.exists():
            shutil.copy2(cached, dest)
            notify_android_media_scanner(dest)
            return dest
        return None

    def fetch_all_user_posts(
        self,
        user_id_or_username: str,
        max_amount: int = 0,
    ) -> list[PostItem]:
        """Fetch all timeline Posts, Carousels, and Reels for a user via v1 API."""
        target = self.normalize_username(user_id_or_username)
        cl = self._ensure_instagrapi()
        if not self._has_live_token():
            self.ensure_default_session()

        uid = target
        real_username = target
        full_name = target
        if not uid.isdigit():
            if target.lower() in self._profiles_cache and self._profiles_cache[target.lower()].user_id:
                prof = self._profiles_cache[target.lower()]
                uid = prof.user_id
                real_username = prof.username
                full_name = prof.full_name or prof.username
            else:
                prof = self.fetch_real_profile(target, download_media=False)
                uid = prof.user_id
                real_username = prof.username
                full_name = prof.full_name or prof.username

        if not uid:
            return []

        posts: list[PostItem] = []
        try:
            raw_medias = cl.user_medias_v1(uid, amount=max(0, max_amount))
            for m in raw_medias or []:
                mpk = str(getattr(m, "pk", "") or "")
                mcode = str(getattr(m, "code", "") or mpk)
                raw_mtype = int(getattr(m, "media_type", 1) or 1)
                prod_type = str(getattr(m, "product_type", "") or "feed")
                if raw_mtype == 8:
                    mtype = "carousel"
                elif raw_mtype == 2 or getattr(m, "video_url", None):
                    mtype = "video"
                else:
                    mtype = "photo"

                taken = getattr(m, "taken_at", None)
                if isinstance(taken, datetime):
                    created_str = taken.strftime("%Y-%m-%d %H:%M:%S")
                    ts_val = int(taken.timestamp())
                else:
                    created_str = str(taken or "Noma'lum")
                    ts_val = 0

                img_url = str(m.thumbnail_url) if getattr(m, "thumbnail_url", None) else None
                vid_url = str(m.video_url) if getattr(m, "video_url", None) else None

                res_list: list[dict[str, Any]] = []
                for r in getattr(m, "resources", None) or []:
                    r_img = str(r.thumbnail_url) if getattr(r, "thumbnail_url", None) else None
                    r_vid = str(r.video_url) if getattr(r, "video_url", None) else None
                    r_pk = str(getattr(r, "pk", "") or "")
                    r_mtype = "video" if (getattr(r, "media_type", 1) == 2 or r_vid) else "photo"
                    res_list.append(
                        {
                            "pk": r_pk,
                            "media_type": r_mtype,
                            "image_url": r_img,
                            "video_url": r_vid,
                        }
                    )
                if not img_url and res_list:
                    img_url = res_list[0].get("image_url")

                play_cnt = int(getattr(m, "play_count", 0) or getattr(m, "view_count", 0) or 0)
                loc_obj = getattr(m, "location", None)
                loc_name = str(getattr(loc_obj, "name", "") or "") if loc_obj else None

                posts.append(
                    PostItem(
                        id=mpk,
                        code=mcode,
                        username=real_username,
                        full_name=full_name,
                        caption=str(getattr(m, "caption_text", "") or ""),
                        like_count=int(getattr(m, "like_count", 0) or 0),
                        comment_count=int(getattr(m, "comment_count", 0) or 0),
                        likes_hidden=bool(getattr(m, "like_and_view_counts_disabled", False)),
                        created_at=created_str,
                        timestamp=ts_val,
                        media_type=mtype,
                        typename=prod_type,
                        product_type=prod_type,
                        image_url=img_url,
                        video_url=vid_url,
                        play_count=play_cnt,
                        resources=res_list,
                        location=loc_name or None,
                    )
                )
        except Exception:
            if target.lower() in self._profiles_cache:
                return self._profiles_cache[target.lower()].posts
        return posts

    def download_by_url_or_shortcode(
        self,
        url_or_code: str,
        target_dir: Optional[Path] = None,
    ) -> list[Path]:
        """
        Download any Instagram resource directly from its URL or shortcode into @<username>/<category>/:
        - /p/<CODE>/ or /reel/<CODE>/ or /tv/<CODE>/ -> @<username>/posts/ or @<username>/reels/
        - /stories/highlights/<ID>/ -> @<username>/highlight/<title>_<id>/
        - /stories/<USERNAME>/... -> @<username>/story/
        """
        raw = url_or_code.strip()

        # 1. Highlight URL
        if "stories/highlights/" in raw or raw.startswith("highlight:"):
            hl = self.fetch_highlight_stories(raw, download_previews=False)
            return self.download_all_highlight_stories(hl, target_dir=target_dir, include_cover=True)

        # 2. Active user story URL: instagram.com/stories/<username>/...
        m_st = re.search(r"instagram\.com/stories/([^/?#]+)", raw)
        if m_st and m_st.group(1).lower() != "highlights":
            st_user = m_st.group(1)
            prof = self.fetch_real_profile(st_user, download_media=False)
            return self.download_all_stories(prof.stories, target_dir=target_dir, username=prof.username)

        # 3. Post / Reel / TV URL or raw shortcode
        code = raw
        m_code = re.search(r"instagram\.com/(?:[^/]+/)?(?:p|reel|reels|tv)/([^/?#]+)", raw)
        if m_code:
            code = m_code.group(1)
        code = code.strip("/")
        if not code:
            raise ValueError("Noto'g'ri Instagram havolasi yoki kod.")

        url = f"https://www.instagram.com/p/{code}/"
        with httpx.Client(
            follow_redirects=True,
            timeout=20.0,
            headers=self.BROWSER_HEADERS,
            cookies=self._get_web_cookies(),
        ) as client:
            resp = client.get(url)

        media_items: list[dict[str, Any]] = []
        for sb in re.findall(r"<script[^>]*>(.*?)</script>", resp.text, re.S):
            if "xdt_api__v1__media__shortcode__web_info" not in sb:
                continue
            try:
                payload = json.loads(sb)

                def _walk(o: Any) -> None:
                    if isinstance(o, dict):
                        w = o.get("xdt_api__v1__media__shortcode__web_info")
                        if isinstance(w, dict) and isinstance(w.get("items"), list):
                            media_items.extend(w["items"])
                        for v in o.values():
                            _walk(v)
                    elif isinstance(o, list):
                        for x in o:
                            _walk(x)

                _walk(payload)
            except Exception:
                pass

        if not media_items:
            raise ValueError(f"Post yoki Reel ({code}) ma'lumotlari topilmadi.")

        it = media_items[0]
        uname = self.normalize_username(str((it.get("user") or {}).get("username") or "instagram")) or "instagram"
        prod_type = str(it.get("product_type") or "")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        saved_files: list[Path] = []

        carousel = it.get("carousel_media") or []
        if carousel:
            downloads_dir = target_dir or get_user_category_dir(uname, "posts")
            downloads_dir.mkdir(parents=True, exist_ok=True)
            for idx, slide in enumerate(carousel, start=1):
                if not isinstance(slide, dict):
                    continue
                vids = slide.get("video_versions") or []
                imgs = (slide.get("image_versions2") or {}).get("candidates") or []
                if vids and isinstance(vids[0], dict) and vids[0].get("url"):
                    dest = downloads_dir / f"{uname}_{code}_slide{idx}_{timestamp}.mp4"
                    b = self._fetch_cdn_bytes(str(vids[0]["url"]), timeout=30.0)
                    if b:
                        dest.write_bytes(b)
                        notify_android_media_scanner(dest)
                        saved_files.append(dest)
                        continue
                if imgs and isinstance(imgs[0], dict) and imgs[0].get("url"):
                    dest = downloads_dir / f"{uname}_{code}_slide{idx}_{timestamp}.jpg"
                    b = self._fetch_cdn_bytes(str(imgs[0]["url"]), timeout=20.0)
                    if b:
                        dest.write_bytes(b)
                        notify_android_media_scanner(dest)
                        saved_files.append(dest)
            return saved_files

        vids = it.get("video_versions") or []
        imgs = (it.get("image_versions2") or {}).get("candidates") or []
        cat_name = "reels" if (prod_type == "clips" or bool(vids)) else "posts"
        downloads_dir = target_dir or get_user_category_dir(uname, cat_name)
        downloads_dir.mkdir(parents=True, exist_ok=True)

        if vids and isinstance(vids[0], dict) and vids[0].get("url"):
            dest = downloads_dir / f"{uname}_{code}_{timestamp}.mp4"
            b = self._fetch_cdn_bytes(str(vids[0]["url"]), timeout=30.0)
            if b:
                dest.write_bytes(b)
                notify_android_media_scanner(dest)
                saved_files.append(dest)
        if imgs and isinstance(imgs[0], dict) and imgs[0].get("url") and not saved_files:
            dest = downloads_dir / f"{uname}_{code}_{timestamp}.jpg"
            b = self._fetch_cdn_bytes(str(imgs[0]["url"]), timeout=20.0)
            if b:
                dest.write_bytes(b)
                notify_android_media_scanner(dest)
                saved_files.append(dest)
        return saved_files

    def export_user_list(
        self,
        username: str,
        list_type: str,
        users: list[UserShort],
        target_dir: Optional[Path] = None,
    ) -> list[Path]:
        """Export followers or following list into @<username>/followers/ (.txt and .json)."""
        clean_u = self.normalize_username(username) or "instagram"
        downloads_dir = target_dir or get_user_category_dir(clean_u, "followers")
        downloads_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        txt_path = downloads_dir / f"{clean_u}_{list_type}_{timestamp}.txt"
        json_path = downloads_dir / f"{clean_u}_{list_type}_{timestamp}.json"

        lines = [
            f"=== @{clean_u} — {list_type.upper()} ({len(users)} ta) ===",
            f"Sana: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "-" * 75,
        ]
        json_rows = []
        for idx, u in enumerate(users, start=1):
            priv = "Private" if u.is_private else "Public"
            ver = "Verified" if u.is_verified else "Unverified"
            link = f"https://www.instagram.com/{u.username}/"
            lines.append(
                f"{idx:4d}. @{u.username:<24} | {u.full_name:<26} | {priv:<7} | {ver:<10} | {link}"
            )
            json_rows.append(
                {
                    "index": idx,
                    "pk": u.pk,
                    "username": u.username,
                    "full_name": u.full_name,
                    "is_private": u.is_private,
                    "is_verified": u.is_verified,
                    "profile_url": link,
                    "profile_pic_url": u.profile_pic_url,
                }
            )

        txt_path.write_text("\n".join(lines), encoding="utf-8")
        json_path.write_text(
            json.dumps(json_rows, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return [txt_path, json_path]

    def export_profile_info(
        self,
        profile: UserProfile,
        target_dir: Optional[Path] = None,
    ) -> list[Path]:
        """Export full profile metadata, bio, links, highlights, and posts summary to @<username>/info/ (.txt and .json)."""
        uname = self.normalize_username(profile.username) or "instagram"
        downloads_dir = target_dir or get_user_category_dir(uname, "info")
        downloads_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        txt_path = downloads_dir / f"{uname}_profile_info_{timestamp}.txt"
        json_path = downloads_dir / f"{uname}_profile_info_{timestamp}.json"

        lines = [
            f"=== INSTAGRAM PROFIL MA'LUMOTLARI: @{profile.username} ===",
            f"To'liq ismi (Full Name): {profile.full_name}",
            f"User ID (PK):            {profile.user_id}",
            f"Graph ID (FBID):         {profile.fbid}",
            f"Verified:                {'Ha' if profile.is_verified else 'Yoq'}",
            f"Maxfiylik (Privacy):     {'Yopiq (Private)' if profile.is_private else 'Ochiq (Public)'}",
            f"Postlar soni:            {profile.media_count}",
            f"Obunachilar (Followers): {profile.follower_count}",
            f"Obunalar (Following):    {profile.following_count}",
            f"Kategoriya:              {profile.category_name or '-'}",
            f"Threads Nishoni:         {profile.text_post_app_badge_label or '-'}",
            f"Biografiya (Bio):        {profile.biography or '-'}",
            f"Bio Havolalar:           {', '.join(profile.bio_links) if profile.bio_links else '-'}",
            f"Profil Havolasi:         {profile.profile_link}",
            f"Faol 24s Storylar:       {len(profile.stories)} ta",
            f"Story Highlights:        {len(profile.highlights)} ta",
            "",
            "--- STORY HIGHLIGHTS ---",
        ]
        for idx, hl in enumerate(profile.highlights, start=1):
            lines.append(
                f"  {idx:2d}. [{hl.id}] {hl.title} ({hl.media_count} ta story, sana: {hl.created_at or '-'})"
            )
        lines.append("")
        lines.append("--- POSTLAR VA REELS ---")
        for idx, p in enumerate(profile.posts, start=1):
            lines.append(
                f"  {idx:2d}. [{p.code}] {p.media_type.upper()} ({p.created_at}) | "
                f"Likes: {p.like_count} | Comments: {p.comment_count} | Views: {p.play_count} | {p.post_url}"
            )
            if p.caption:
                lines.append(f"      Caption: {p.caption}")

        txt_path.write_text("\n".join(lines), encoding="utf-8")

        summary_json = {
            "username": profile.username,
            "full_name": profile.full_name,
            "user_id": profile.user_id,
            "fbid": profile.fbid,
            "is_verified": profile.is_verified,
            "is_private": profile.is_private,
            "media_count": profile.media_count,
            "follower_count": profile.follower_count,
            "following_count": profile.following_count,
            "category_name": profile.category_name,
            "biography": profile.biography,
            "bio_links": profile.bio_links,
            "profile_link": profile.profile_link,
            "profile_pic_url": profile.profile_pic_url,
            "active_stories_count": len(profile.stories),
            "highlights": [
                {
                    "id": h.id,
                    "title": h.title,
                    "media_count": h.media_count,
                    "created_at": h.created_at,
                    "cover_url": h.cover_url,
                }
                for h in profile.highlights
            ],
            "posts": [
                {
                    "id": p.id,
                    "code": p.code,
                    "media_type": p.media_type,
                    "product_type": p.product_type,
                    "created_at": p.created_at,
                    "like_count": p.like_count,
                    "comment_count": p.comment_count,
                    "play_count": p.play_count,
                    "caption": p.caption,
                    "post_url": p.post_url,
                    "image_url": p.image_url,
                    "video_url": p.video_url,
                }
                for p in profile.posts
            ],
            "raw_data": profile.raw_data,
        }
        json_path.write_text(
            json.dumps(summary_json, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return [txt_path, json_path]

    def download_everything_for_profile(
        self,
        profile: UserProfile,
        include_followers: bool = True,
    ) -> dict[str, list[Path]]:
        """
        Download EVERY SINGLE available item for a profile into an organized folder structure
        under <downloads_dir>/@<username>/:
        - avatar/       (Full HD Avatar)
        - story/        (All active 24h Stories: MP4 & JPG)
        - highlight/    (All Highlight covers + all inner MP4 & JPG stories)
        - posts/        (All timeline Photos and Carousel slides)
        - reels/        (All Reels and Video posts)
        - followers/    (Complete followers & following lists in .txt and .json)
        - info/         (Complete profile metadata & bio in .txt and .json)
        """
        uname = self.normalize_username(profile.username) or "instagram"
        get_user_download_dir(uname)

        results: dict[str, list[Path]] = {
            "avatar": [],
            "stories_24h": [],
            "highlights": [],
            "posts_and_reels": [],
            "followers_following": [],
            "info": [],
        }

        # 1. Profile Info -> @<username>/info/
        try:
            info_dir = get_user_category_dir(uname, "info")
            results["info"].extend(self.export_profile_info(profile, target_dir=info_dir))
        except Exception:
            pass

        # 2. Full HD Avatar -> @<username>/avatar/
        try:
            avatar_dir = get_user_category_dir(uname, "avatar")
            av = self.save_media_to_downloads(
                profile.profile_pic_url or profile.local_avatar_path,
                f"{uname}_avatar_hd",
                target_dir=avatar_dir,
                username=uname,
                category="avatar",
            )
            if av:
                results["avatar"].append(av)
        except Exception:
            pass

        # 3. Active 24-hour Stories -> @<username>/story/
        if profile.stories:
            stories_dir = get_user_category_dir(uname, "story")
            try:
                results["stories_24h"].extend(
                    self.download_all_stories(profile.stories, target_dir=stories_dir, username=uname)
                )
            except Exception:
                pass

        # 4. All Story Highlights -> @<username>/highlight/<01_Title_ID>/
        if profile.highlights:
            for idx, hl_meta in enumerate(profile.highlights, start=1):
                safe_title = self._sanitize_filename(hl_meta.title)
                hl_dir = get_user_category_dir(
                    uname,
                    "highlight",
                    subfolder=f"{idx:02d}_{safe_title}_{hl_meta.id}",
                )
                try:
                    hl_det = self.fetch_highlight_stories(
                        hl_meta.id,
                        download_previews=False,
                        fallback_highlight=hl_meta,
                    )
                    results["highlights"].extend(
                        self.download_all_highlight_stories(
                            hl_det,
                            target_dir=hl_dir,
                            include_cover=True,
                        )
                    )
                except Exception:
                    continue

        # 5. All Timeline Posts, Reels, and Carousel Albums -> @<username>/posts/ and @<username>/reels/
        all_posts = profile.posts
        if profile.media_count > len(all_posts) and not profile.is_private:
            fetched_all = self.fetch_all_user_posts(profile.user_id or profile.username, max_amount=0)
            if fetched_all:
                all_posts = fetched_all
                profile.posts = fetched_all

        if all_posts:
            for p in all_posts:
                try:
                    results["posts_and_reels"].extend(
                        self.download_all_post_media(p)
                    )
                except Exception:
                    continue

        # 6. Followers and Following Lists (.txt + .json) -> @<username>/followers/
        if include_followers and (profile.follower_count > 0 or profile.following_count > 0):
            ff_dir = get_user_category_dir(uname, "followers")
            if profile.follower_count > 0:
                try:
                    followers = self.get_user_followers(
                        profile.user_id or profile.username,
                        amount=0,
                    )
                    if followers:
                        results["followers_following"].extend(
                            self.export_user_list(
                                profile.username,
                                "followers",
                                followers,
                                target_dir=ff_dir,
                            )
                        )
                except Exception:
                    pass
            if profile.following_count > 0:
                try:
                    following = self.get_user_following(
                        profile.user_id or profile.username,
                        amount=0,
                    )
                    if following:
                        results["followers_following"].extend(
                            self.export_user_list(
                                profile.username,
                                "following",
                                following,
                                target_dir=ff_dir,
                            )
                        )
                except Exception:
                    pass

        return results

    def get_user_followers(
        self,
        user_id_or_username: str,
        amount: int = 0,
    ) -> list[UserShort]:
        """
        Fetch the real followers list (obunachilar) for a user.
        Uses authenticated instagrapi endpoint (amount=0 fetches all accessible followers).
        """
        target = self.normalize_username(user_id_or_username)
        cl = self._ensure_instagrapi()
        if not self._has_live_token():
            self.ensure_default_session()

        uid = target
        if not uid.isdigit():
            if target.lower() in self._profiles_cache and self._profiles_cache[target.lower()].user_id:
                uid = self._profiles_cache[target.lower()].user_id
            else:
                prof = self.fetch_real_profile(target, download_media=False)
                uid = prof.user_id

        if not uid:
            raise ValueError(f"@{target} uchun Instagram User ID (PK) aniqlanmadi.")

        try:
            raw_users = cl.user_followers_v1(uid, amount=max(0, amount))
            res: list[UserShort] = []
            for u in raw_users:
                res.append(
                    UserShort(
                        pk=str(u.pk),
                        username=str(u.username),
                        full_name=str(u.full_name or ""),
                        profile_pic_url=str(u.profile_pic_url) if getattr(u, "profile_pic_url", None) else None,
                        is_private=bool(getattr(u, "is_private", False)),
                        is_verified=bool(getattr(u, "is_verified", False)),
                    )
                )
            return res
        except Exception as exc:
            raise RuntimeError(f"Obunachilarni olishda xatolik: {exc}") from exc

    def get_user_following(
        self,
        user_id_or_username: str,
        amount: int = 0,
    ) -> list[UserShort]:
        """
        Fetch the real following list (obunalar / kimlarga obuna bo'lganligi) for a user.
        Uses authenticated instagrapi endpoint (amount=0 fetches all accessible followings).
        """
        target = self.normalize_username(user_id_or_username)
        cl = self._ensure_instagrapi()
        if not self._has_live_token():
            self.ensure_default_session()

        uid = target
        if not uid.isdigit():
            if target.lower() in self._profiles_cache and self._profiles_cache[target.lower()].user_id:
                uid = self._profiles_cache[target.lower()].user_id
            else:
                prof = self.fetch_real_profile(target, download_media=False)
                uid = prof.user_id

        if not uid:
            raise ValueError(f"@{target} uchun Instagram User ID (PK) aniqlanmadi.")

        try:
            raw_users = cl.user_following_v1(uid, amount=max(0, amount))
            res: list[UserShort] = []
            for u in raw_users:
                res.append(
                    UserShort(
                        pk=str(u.pk),
                        username=str(u.username),
                        full_name=str(u.full_name or ""),
                        profile_pic_url=str(u.profile_pic_url) if getattr(u, "profile_pic_url", None) else None,
                        is_private=bool(getattr(u, "is_private", False)),
                        is_verified=bool(getattr(u, "is_verified", False)),
                    )
                )
            return res
        except Exception as exc:
            raise RuntimeError(f"Obunalarni olishda xatolik: {exc}") from exc

    def open_in_system_viewer(self, file_path: Path) -> None:
        """Open a downloaded/cached file in the operating system's default viewer (Windows, macOS, Linux, Android Termux)."""
        if not file_path or not file_path.exists():
            return
        notify_android_media_scanner(file_path)
        try:
            if is_termux() and shutil.which("termux-open"):
                subprocess.Popen(
                    ["termux-open", str(file_path)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            elif sys.platform == "win32":
                os.startfile(str(file_path))  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(file_path)])
            elif shutil.which("xdg-open"):
                subprocess.Popen(["xdg-open", str(file_path)])
        except Exception:
            pass
