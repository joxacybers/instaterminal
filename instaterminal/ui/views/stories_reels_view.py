"""Stories and Reels View with terminal preview, user filter, and media downloader/player."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Button, Input, Static

from instaterminal.core.client import InstaClientService
from instaterminal.core.image_renderer import TerminalImageRenderer
from instaterminal.core.models import ReelItem, StoryItem


class StoriesReelsView(Vertical):
    """View active Stories and Reels with terminal preview, search by user, download, and OS playback."""

    def __init__(self, service: InstaClientService) -> None:
        super().__init__(id="stories-reels-view")
        self.service = service
        self._story_map: dict[str, StoryItem] = {}
        self._reel_map: dict[str, ReelItem] = {}

    def compose(self) -> ComposeResult:
        with Horizontal(id="profile-search-bar"):
            yield Input(
                placeholder="🔍 Foydalanuvchi Stories/Reels qidirish (masalan: samarqand_travel)...",
                id="stories-user-input",
            )
            yield Button("🔍 Yuklash", id="btn-stories-search", variant="primary")
            yield Button("🔄 Barchasi", id="btn-stories-reset", variant="warning")

        with VerticalScroll(id="stories-reels-scroll"):
            yield Static("⚡ Faol Stories (24 soatlik lavhalar)", classes="section-header")
            yield Vertical(id="stories-container")
            yield Static("🎬 Reels (Qisqa videolar)", classes="section-header")
            yield Vertical(id="reels-container")

    def on_mount(self) -> None:
        self.refresh_content()

    def refresh_content(self, username: str | None = None) -> None:
        stories_box = self.query_one("#stories-container", Vertical)
        reels_box = self.query_one("#reels-container", Vertical)
        stories_box.remove_children()
        reels_box.remove_children()

        self._story_map.clear()
        self._reel_map.clear()

        for st in self.service.get_stories(username=username):
            self._story_map[st.id] = st
            img_path = st.local_image_path or TerminalImageRenderer.generate_procedural_image(
                st.id, theme="sunset"
            )
            art = TerminalImageRenderer.render_image(img_path, width=44, max_height=14)
            badge = "🎥 VIDEO STORY" if st.media_type == "video" else "🖼️ PHOTO STORY"
            card = Vertical(
                Static(
                    f"{badge}  •  @{st.username} ({st.full_name})  •  🕒 {st.taken_at}  •  👁️ {st.view_count} ko'rish",
                    classes="post-header",
                ),
                Static(art, classes="post-image-box"),
                Static(st.caption, classes="post-caption"),
                Horizontal(
                    Button(
                        "⬇️ Yuklab olish",
                        name=f"dl-story:{st.id}",
                        variant="success",
                    ),
                    Button(
                        "▶️ Pleyerda ochish",
                        name=f"play-story:{st.id}",
                        variant="primary",
                    ),
                    classes="post-actions-row",
                ),
                classes="media-card",
            )
            stories_box.mount(card)

        for rl in self.service.get_reels(username=username):
            self._reel_map[rl.id] = rl
            img_path = rl.local_image_path or TerminalImageRenderer.generate_procedural_image(
                rl.id, theme="neon"
            )
            art = TerminalImageRenderer.render_image(img_path, width=44, max_height=14)
            card = Vertical(
                Static(
                    f"🎬 REEL @{rl.username} ({rl.full_name})  •  ⏱️ {rl.duration_seconds}s  •  ▶️ {rl.play_count:,} marta ko'rilgan",
                    classes="post-header",
                ),
                Static(art, classes="post-image-box"),
                Static(rl.caption, classes="post-caption"),
                Static(
                    f"❤️ {rl.like_count:,} layk   •   💬 {rl.comment_count:,} izoh   •   🔖 {rl.code}",
                    classes="post-stats",
                ),
                Horizontal(
                    Button(
                        "⬇️ Reel-ni saqlash",
                        name=f"dl-reel:{rl.id}",
                        variant="success",
                    ),
                    Button(
                        "▶️ Pleyerda ochish",
                        name=f"play-reel:{rl.id}",
                        variant="primary",
                    ),
                    classes="post-actions-row",
                ),
                classes="media-card",
            )
            reels_box.mount(card)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        btn_id = event.button.id or ""
        btn_name = event.button.name or ""

        if btn_id == "btn-stories-search":
            event.stop()
            q = self.query_one("#stories-user-input", Input).value.strip()
            self.refresh_content(username=q or None)
            self.app.notify(f"Stories & Reels yuklandi: {q or 'Barchasi'}")
        elif btn_id == "btn-stories-reset":
            event.stop()
            self.query_one("#stories-user-input", Input).value = ""
            self.refresh_content(username=None)
            self.app.notify("Barcha Stories & Reels ko'rsatilmoqda")
        elif btn_name.startswith("dl-story:"):
            event.stop()
            sid = btn_name.removeprefix("dl-story:")
            item = self._story_map.get(sid)
            if item:
                saved = self.service.download_media_item(item)
                self.app.notify(f"Story saqlandi: {saved}", title="⬇️ Story Yuklandi")
        elif btn_name.startswith("play-story:"):
            event.stop()
            sid = btn_name.removeprefix("play-story:")
            item = self._story_map.get(sid)
            if item:
                saved = self.service.open_in_system_viewer(item)
                self.app.notify(f"Tizim dasturida ochildi: {saved.name}", title="▶️ Ochildi")
        elif btn_name.startswith("dl-reel:"):
            event.stop()
            rid = btn_name.removeprefix("dl-reel:")
            item = self._reel_map.get(rid)
            if item:
                saved = self.service.download_media_item(item)
                self.app.notify(f"Reel saqlandi: {saved}", title="⬇️ Reel Yuklandi")
        elif btn_name.startswith("play-reel:"):
            event.stop()
            rid = btn_name.removeprefix("play-reel:")
            item = self._reel_map.get(rid)
            if item:
                saved = self.service.open_in_system_viewer(item)
                self.app.notify(f"Tizim dasturida ochildi: {saved.name}", title="▶️ Ochildi")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "stories-user-input":
            event.stop()
            q = event.input.value.strip()
            self.refresh_content(username=q or None)
