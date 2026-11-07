"""Feed View displaying interactive timeline posts."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Button, Static

from instaterminal.core.client import InstaClientService
from instaterminal.ui.widgets.post_card import PostCard


class FeedView(Vertical):
    """Scrollable Instagram Feed view with refresh and upload triggers."""

    def __init__(self, service: InstaClientService) -> None:
        super().__init__(id="feed-view")
        self.service = service
        self.default_mode = "unicode"

    def compose(self) -> ComposeResult:
        with Horizontal(classes="post-actions-row"):
            yield Static("🏠 Asosiy Lenta (Timeline Feed)", classes="section-header")
            yield Button("🔄 Yangilash", id="btn-feed-refresh", variant="primary")
            yield Button("➕ Yangi Post (N)", id="btn-feed-upload", variant="success")
            yield Button("🎨 Barchasini ASCII/HD", id="btn-feed-toggle-all", variant="warning")

        yield VerticalScroll(id="feed-scroll")

    def on_mount(self) -> None:
        self.refresh_feed()

    def refresh_feed(self) -> None:
        """Reload timeline posts into the scroll container."""
        scroll = self.query_one("#feed-scroll", VerticalScroll)
        scroll.remove_children()
        posts = self.service.get_timeline_feed()
        if not posts:
            scroll.mount(Static("Hozircha postlar topilmadi.", classes="post-caption"))
            return
        for post in posts:
            scroll.mount(
                PostCard(
                    post=post,
                    service=self.service,
                    render_mode=self.default_mode,
                    image_width=52,
                )
            )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        btn_id = event.button.id or ""
        if btn_id == "btn-feed-refresh":
            event.stop()
            self.refresh_feed()
            self.app.notify("🔄 Lenta yangilandi!")
        elif btn_id == "btn-feed-upload":
            event.stop()
            self.app.action_new_post()  # type: ignore[attr-defined]
        elif btn_id == "btn-feed-toggle-all":
            event.stop()
            self.default_mode = "ascii" if self.default_mode == "unicode" else "unicode"
            self.refresh_feed()
            self.app.notify(
                f"Tasvir rejimi: {'🎨 ASCII Art' if self.default_mode == 'ascii' else '🌈 HD Unicode'}"
            )

