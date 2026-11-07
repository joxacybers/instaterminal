"""Profile and User Search View displaying user bio, statistics, avatar, and posts."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Button, Input, Static

from instaterminal.core.client import InstaClientService
from instaterminal.core.image_renderer import TerminalImageRenderer
from instaterminal.core.models import UserProfile
from instaterminal.ui.widgets.post_card import PostCard


class ProfileView(Vertical):
    """Search for any Instagram user or inspect your own profile and posts."""

    def __init__(self, service: InstaClientService) -> None:
        super().__init__(id="profile-view")
        self.service = service

    def compose(self) -> ComposeResult:
        with Horizontal(id="profile-search-bar"):
            yield Input(
                placeholder="🔍 Username qidiring (masalan: samarqand_travel, tashkent_devs, nature_uzb)...",
                id="profile-search-input",
            )
            yield Button("🔍 Qidirish", id="btn-profile-search", variant="primary")
            yield Button("👤 Mening Profilim", id="btn-my-profile", variant="success")

        with VerticalScroll(id="profile-scroll"):
            yield Vertical(id="profile-header-card")
            yield Static("📸 Foydalanuvchi Postlari", classes="section-header")
            yield Vertical(id="profile-posts-container")

    def on_mount(self) -> None:
        self.load_profile(self.service.username or "argon_coder")

    def load_profile(self, username: str) -> None:
        """Render the specified user's profile header and recent posts."""
        profile: UserProfile = self.service.get_user_profile(username)
        header_card = self.query_one("#profile-header-card", Vertical)
        posts_box = self.query_one("#profile-posts-container", Vertical)
        header_card.remove_children()
        posts_box.remove_children()

        avatar_path = profile.local_avatar_path or TerminalImageRenderer.generate_procedural_image(
            profile.username, theme="cyber"
        )
        avatar_art = TerminalImageRenderer.render_image(avatar_path, width=24, max_height=10)

        verified_badge = " ✔️" if profile.is_verified else ""
        privacy_badge = " 🔒 Yopiq profil" if profile.is_private else " 🌐 Ochiq profil"
        url_line = f"\n🔗 Havola: {profile.external_url}" if profile.external_url else ""

        info_text = (
            f"👤 @{profile.username}{verified_badge}  —  {profile.full_name} ({privacy_badge})\n\n"
            f"📊 Postlar: {profile.media_count:,}   •   "
            f"👥 Obunachilar (Followers): {profile.follower_count:,}   •   "
            f"👣 Obunalar (Following): {profile.following_count:,}\n\n"
            f"📝 Bio:\n{profile.biography}{url_line}"
        )

        header_card.mount(
            Horizontal(
                Static(avatar_art, classes="post-image-box"),
                Static(info_text, classes="post-caption"),
            )
        )

        if not profile.posts:
            posts_box.mount(Static("Bu profilda hozircha postlar yo'q.", classes="post-caption"))
        else:
            for p in profile.posts:
                posts_box.mount(
                    PostCard(
                        post=p,
                        service=self.service,
                        render_mode="unicode",
                        image_width=48,
                    )
                )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        btn_id = event.button.id or ""
        if btn_id == "btn-profile-search":
            event.stop()
            self._run_search()
        elif btn_id == "btn-my-profile":
            event.stop()
            self.load_profile(self.service.username or "argon_coder")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "profile-search-input":
            event.stop()
            self._run_search()

    def _run_search(self) -> None:
        inp = self.query_one("#profile-search-input", Input)
        q = inp.value.strip()
        if not q:
            self.app.notify("Qidiruv uchun username kiriting!", severity="warning")
            return
        results = self.service.search_users(q)
        if results:
            self.load_profile(results[0].username)
            self.app.notify(f"✅ @{results[0].username} profili yuklandi!")
        else:
            self.app.notify(f"'{q}' bo'yicha foydalanuvchi topilmadi.", severity="warning")

