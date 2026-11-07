"""Real Instagram data models for InstaTerminal."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional


@dataclass
class UserShort:
    pk: str
    username: str
    full_name: str
    profile_pic_url: Optional[str] = None
    is_private: bool = False
    is_verified: bool = False
    is_bestie: bool = False
    latest_reel_media: int = 0


@dataclass
class StoryItem:
    id: str
    username: str
    full_name: str
    taken_at: str
    code: str = ""
    media_type: str = "photo"  # "photo" or "video"
    dimensions: str = ""
    video_duration: float = 0.0
    has_audio: bool = False
    image_url: Optional[str] = None
    video_url: Optional[str] = None
    local_image_path: Optional[Path] = None
    local_video_path: Optional[Path] = None
    caption: str = ""
    accessibility_caption: str = ""
    view_count: int = 0


@dataclass
class HighlightItem:
    id: str
    title: str
    owner_username: str = ""
    cover_url: Optional[str] = None
    local_cover_path: Optional[Path] = None
    latest_reel_media: int = 0
    media_count: int = 0
    created_at: str = ""
    is_pinned: bool = False
    items: list[StoryItem] = field(default_factory=list)


@dataclass
class CommentItem:
    id: str
    username: str
    text: str
    created_at: str
    likes_count: int = 0


@dataclass
class PostItem:
    id: str
    code: str
    username: str
    full_name: str
    caption: str
    like_count: int
    comment_count: int
    created_at: str
    media_type: str = "photo"  # "photo", "video", "carousel"
    typename: str = ""
    product_type: str = "feed"
    accessibility_caption: str = ""
    commenter_count: int = 0
    likes_hidden: bool = False
    timestamp: int = 0
    dimensions: str = ""
    is_paid_partnership: bool = False
    is_affiliate: bool = False
    is_pinned: bool = False
    coauthors: list[str] = field(default_factory=list)
    image_url: Optional[str] = None
    video_url: Optional[str] = None
    local_image_path: Optional[Path] = None
    play_count: int = 0
    resources: list[dict[str, Any]] = field(default_factory=list)
    has_liked: bool = False
    location: Optional[str] = None
    comments: list[CommentItem] = field(default_factory=list)

    @property
    def post_url(self) -> str:
        return f"https://www.instagram.com/p/{self.code}/" if self.code else ""


@dataclass
class ReelItem:
    id: str
    code: str
    username: str
    full_name: str
    caption: str
    play_count: int
    like_count: int
    comment_count: int
    duration_seconds: int = 15
    image_url: Optional[str] = None
    video_url: Optional[str] = None
    local_image_path: Optional[Path] = None
    has_liked: bool = False


@dataclass
class DirectMessage:
    id: str
    sender_username: str
    text: str
    timestamp: str
    is_me: bool = False


@dataclass
class DirectThread:
    id: str
    title: str
    participants: list[str]
    last_message: str
    updated_at: str
    unread: bool = False
    messages: list[DirectMessage] = field(default_factory=list)


@dataclass
class UserProfile:
    user_id: str
    username: str
    full_name: str
    biography: str
    follower_count: int
    following_count: int
    media_count: int
    fbid: str = ""
    is_private: bool = False
    is_verified: bool = False
    is_memorialized: bool = False
    is_unpublished: bool = False
    is_coppa_enforced: bool = False
    has_public_story: bool = False
    has_any_clips: bool = False
    latest_reel_media: int = 0
    show_text_post_app_badge: bool = False
    text_post_app_badge_label: str = ""
    pronouns: list[str] = field(default_factory=list)
    bio_links: list[str] = field(default_factory=list)
    account_badges: list[str] = field(default_factory=list)
    external_url: Optional[str] = None
    profile_pic_url: Optional[str] = None
    local_avatar_path: Optional[Path] = None
    profile_link: str = ""
    request_id: str = ""
    category_name: str = ""
    public_email: str = ""
    contact_phone_number: str = ""
    stories: list[StoryItem] = field(default_factory=list)
    highlights: list[HighlightItem] = field(default_factory=list)
    posts: list[PostItem] = field(default_factory=list)
    raw_data: dict[str, Any] = field(default_factory=dict)
