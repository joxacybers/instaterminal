"""Modal dialog for uploading a new Instagram photo post with live terminal preview."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Static

from instaterminal.core.client import InstaClientService
from instaterminal.core.image_renderer import TerminalImageRenderer
from instaterminal.core.models import PostItem


class UploadModal(ModalScreen[Optional[PostItem]]):
    """Modal dialog to preview and publish a new photo post."""

    BINDINGS = [
        ("escape", "cancel", "Bekor qilish"),
    ]

    def __init__(self, service: InstaClientService) -> None:
        super().__init__()
        self.service = service
        self._sample_path: Path = TerminalImageRenderer.generate_procedural_image(
            "new_upload_sample", theme="neon"
        )

    def compose(self) -> ComposeResult:
        with Vertical(id="upload-dialog"):
            yield Static("➕ Yangi Instagram Post Yuklash", classes="section-header")
            yield Label("📁 Rasm fayli manzili (bo'sh qoldirilsa namuna rasm ishlatiladi):")
            with Horizontal(classes="comment-input-row"):
                yield Input(
                    value=str(self._sample_path),
                    placeholder="C:/path/to/photo.jpg",
                    id="upload-file-input",
                )
                yield Button("👁️ Ko'rish", id="btn-preview-img", variant="primary")
                yield Button("🎲 Yangi Art", id="btn-gen-art", variant="warning")

            yield Static(
                TerminalImageRenderer.render_image(self._sample_path, width=44, max_height=14),
                id="upload-preview-box",
            )

            yield Label("📝 Post matni (Caption):")
            yield Input(
                placeholder="Post haqida izoh va #heshteglar yozing...",
                value="InstaTerminal TUI orqali terminaldan yuklandi! 🚀✨ #InstaTerminal #Python",
                id="upload-caption-input",
            )

            with Horizontal(id="login-actions"):
                yield Button("📤 Joylash (Publish)", id="btn-upload-submit", variant="success")
                yield Button("✖ Bekor qilish (Esc)", id="btn-upload-cancel", variant="error")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        btn_id = event.button.id or ""
        if btn_id == "btn-upload-cancel":
            self.action_cancel()
        elif btn_id == "btn-preview-img":
            self._update_preview()
        elif btn_id == "btn-gen-art":
            self._generate_random_art()
        elif btn_id == "btn-upload-submit":
            self._submit_post()

    def _update_preview(self) -> None:
        file_str = self.query_one("#upload-file-input", Input).value.strip()
        preview_box = self.query_one("#upload-preview-box", Static)
        p = Path(file_str).expanduser()
        if not p.exists() or not p.is_file():
            preview_box.update(f"⚠️ Fayl topilmadi: {p}")
            return
        preview_box.update(TerminalImageRenderer.render_image(p, width=44, max_height=14))

    def _generate_random_art(self) -> None:
        import time

        themes = ["sunset", "cyber", "emerald", "neon", "desert"]
        chosen = themes[int(time.time() * 10) % len(themes)]
        art_path = TerminalImageRenderer.generate_procedural_image(
            f"art_{time.time()}", theme=chosen
        )
        self._sample_path = art_path
        self.query_one("#upload-file-input", Input).value = str(art_path)
        self.query_one("#upload-preview-box", Static).update(
            TerminalImageRenderer.render_image(art_path, width=44, max_height=14)
        )

    def _submit_post(self) -> None:
        file_str = self.query_one("#upload-file-input", Input).value.strip()
        caption = self.query_one("#upload-caption-input", Input).value.strip()
        target_path = Path(file_str).expanduser() if file_str else self._sample_path

        try:
            new_post = self.service.upload_photo_post(target_path, caption)
            self.app.notify("✅ Yangi post muvaffaqiyatli joylandi!", title="📤 Yuklandi")
            self.dismiss(new_post)
        except Exception as exc:
            self.app.notify(f"Xatolik: {exc}", severity="error")

    def action_cancel(self) -> None:
        self.dismiss(None)

