"""Interactive Post Card widget with Unicode/ASCII image toggle, Like, Comment, and Download."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.widgets import Button, Input, Static

from instaterminal.core.client import InstaClientService
from instaterminal.core.image_renderer import TerminalImageRenderer
from instaterminal.core.models import PostItem


class PostCard(Vertical):
    """Displays a single Instagram post inside the terminal without global ID collisions."""

    class PostUpdated(Message):
        """Dispatched when a post is liked or commented on."""

        def __init__(self, post: PostItem) -> None:
            super().__init__()
            self.post = post

    def __init__(
        self,
        post: PostItem,
        service: InstaClientService,
        render_mode: str = "unicode",
        image_width: int = 52,
    ) -> None:
        super().__init__()
        self.post = post
        self.service = service
        self.render_mode = render_mode
        self.image_width = image_width

        self._img_widget = Static(classes="post-image-box")
        self._stats_widget = Static(classes="post-stats")
        self._comments_widget = Static(classes="post-comments-box")
        self._like_btn = Button(
            "❤️ Layk bosilgan" if self.post.has_liked else "🤍 Layk",
            variant="error" if self.post.has_liked else "default",
            name="like",
        )
        self._mode_btn = Button(
            "🎨 ASCII rejim" if self.render_mode == "unicode" else "🌈 HD Unicode",
            variant="primary",
            name="mode",
        )
        self._dl_btn = Button("⬇️ Saqlash", variant="success", name="download")
        self._comment_input = Input(placeholder="💬 Izoh yozing va Enter bosing...")
        self._comment_btn = Button("Yuborish", variant="warning", name="comment")

    def compose(self) -> ComposeResult:
        loc_suffix = f"  •  📍 {self.post.location}" if self.post.location else ""
        header_text = (
            f"📸 @{self.post.username} ({self.post.full_name})"
            f"  •  🕒 {self.post.created_at}{loc_suffix}"
        )
        yield Static(header_text, classes="post-header")

        self._img_widget.update(self._render_visual())
        self._stats_widget.update(self._format_stats())
        self._comments_widget.update(self._format_comments())

        yield self._img_widget
        yield Static(self.post.caption, classes="post-caption")
        yield self._stats_widget
        yield self._comments_widget

        with Horizontal(classes="post-actions-row"):
            yield self._like_btn
            yield self._mode_btn
            yield self._dl_btn

        with Horizontal(classes="comment-input-row"):
            yield self._comment_input
            yield self._comment_btn

    def _render_visual(self):
        path = self.post.local_image_path
        if path and path.exists():
            return TerminalImageRenderer.render_image(
                path,
                width=self.image_width,
                max_height=20,
                mode=self.render_mode,
            )
        fallback = TerminalImageRenderer.generate_procedural_image(self.post.id, theme="sunset")
        self.post.local_image_path = fallback
        return TerminalImageRenderer.render_image(
            fallback,
            width=self.image_width,
            max_height=20,
            mode=self.render_mode,
        )

    def _format_stats(self) -> str:
        heart = "❤️" if self.post.has_liked else "🤍"
        return (
            f"{heart} {self.post.like_count:,} ta layk   •   "
            f"💬 {self.post.comment_count:,} ta izoh   •   "
            f"🔖 Kod: {self.post.code}"
        )

    def _format_comments(self) -> str:
        if not self.post.comments:
            return "💬 Hozircha izohlar yo'q. Birinchi bo'lib fikr bildiring!"
        lines = ["💬 Oxirgi izohlar:"]
        for c in self.post.comments[-4:]:
            lines.append(f"  • @{c.username}: {c.text} ({c.created_at})")
        return "\n".join(lines)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        btn_name = event.button.name or ""
        if btn_name == "like":
            event.stop()
            self._handle_like()
        elif btn_name == "mode":
            event.stop()
            self._handle_toggle_mode()
        elif btn_name == "download":
            event.stop()
            self._handle_download()
        elif btn_name == "comment":
            event.stop()
            self._submit_comment()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input is self._comment_input:
            event.stop()
            self._submit_comment()

    def _handle_like(self) -> None:
        updated = self.service.toggle_like(self.post.id)
        if updated:
            self.post = updated
        self._stats_widget.update(self._format_stats())

        self._like_btn.label = "❤️ Layk bosilgan" if self.post.has_liked else "🤍 Layk"
        self._like_btn.variant = "error" if self.post.has_liked else "default"
        self.app.notify(
            f"@{self.post.username} postiga {'❤️ layk bosildi!' if self.post.has_liked else 'layk qaytarib olindi.'}"
        )
        self.post_message(self.PostUpdated(self.post))

    def _handle_toggle_mode(self) -> None:
        self.render_mode = "ascii" if self.render_mode == "unicode" else "unicode"
        self._img_widget.update(self._render_visual())
        self._mode_btn.label = (
            "🎨 ASCII rejim" if self.render_mode == "unicode" else "🌈 HD Unicode"
        )

    def _handle_download(self) -> None:
        saved_path = self.service.download_media_item(self.post)
        self.app.notify(f"Media saqlandi: {saved_path}", title="⬇️ Yuklab olindi")

    def _submit_comment(self) -> None:
        text = self._comment_input.value.strip()
        if not text:
            self.app.notify("Izoh matnini kiriting!", severity="warning")
            return
        self.service.add_comment(self.post.id, text)
        self._comment_input.value = ""
        self._stats_widget.update(self._format_stats())
        self._comments_widget.update(self._format_comments())
        self.app.notify("💬 Izohingiz qo'shildi!")
        self.post_message(self.PostUpdated(self.post))
