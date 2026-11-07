"""Direct Messages (DM) View with thread list, new chat creation, and real-time chat pane."""

from __future__ import annotations

from typing import Optional

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Button, Input, ListItem, ListView, Static

from instaterminal.core.client import InstaClientService
from instaterminal.core.models import DirectThread


class DirectMessagesView(Vertical):
    """Two-column Direct Messages interface supporting starting new threads and live messaging."""

    def __init__(self, service: InstaClientService) -> None:
        super().__init__(id="dm-view")
        self.service = service
        self._threads: list[DirectThread] = []
        self._active_thread_id: Optional[str] = None

    def compose(self) -> ComposeResult:
        with Horizontal(id="dm-split"):
            with Vertical(id="dm-threads-pane"):
                yield Static("💬 Suhbatlar (Direct)", classes="section-header")
                yield Input(
                    placeholder="➕ @username yozib Enter (yangi chat)...",
                    id="dm-new-user-input",
                )
                yield ListView(id="dm-thread-list")
                yield Button("🔄 Yangilash", id="btn-dm-refresh", variant="primary")

            with Vertical(id="dm-chat-pane"):
                yield Static("📨 Suhbatni tanlang", id="dm-active-title", classes="section-header")
                yield VerticalScroll(id="dm-messages-scroll")
                with Horizontal(id="dm-compose-row"):
                    yield Input(
                        placeholder="✉️ Xabar yozing va Enter bosing...",
                        id="dm-message-input",
                    )
                    yield Button("Yuborish ➤", id="btn-dm-send", variant="success")

    def on_mount(self) -> None:
        self.refresh_threads()

    def refresh_threads(self) -> None:
        """Load DM threads into the left ListView."""
        self._threads = self.service.get_direct_threads()
        list_view = self.query_one("#dm-thread-list", ListView)
        list_view.clear()

        for t in self._threads:
            unread_dot = "🟢 " if t.unread else "💬 "
            preview = t.last_message[:26] + ("…" if len(t.last_message) > 26 else "")
            item_label = f"{unread_dot}{t.title}\n   {preview} ({t.updated_at})"
            list_view.append(ListItem(Static(item_label), name=t.id))

        if self._threads and not self._active_thread_id:
            self._select_thread(self._threads[0].id)
        elif self._active_thread_id:
            self._select_thread(self._active_thread_id)

    def _select_thread(self, thread_id: str) -> None:
        self._active_thread_id = thread_id
        thread = next((t for t in self._threads if t.id == thread_id), None)
        title_widget = self.query_one("#dm-active-title", Static)
        msg_scroll = self.query_one("#dm-messages-scroll", VerticalScroll)
        msg_scroll.remove_children()

        if not thread:
            title_widget.update("📨 Suhbat topilmadi")
            return

        thread.unread = False
        title_widget.update(
            f"📨 {thread.title}  •  Ishtirokchilar: {', '.join('@' + u for u in thread.participants)}"
        )

        if not thread.messages:
            msg_scroll.mount(Static("Bu suhbatda hali xabarlar yo'q.", classes="msg-other"))
            return

        for m in thread.messages:
            prefix = "🧑 Siz" if m.is_me else f"👤 @{m.sender_username}"
            css_cls = "msg-me" if m.is_me else "msg-other"
            line = f"[{m.timestamp}] {prefix}: {m.text}"
            msg_scroll.mount(Static(line, classes=css_cls))

        msg_scroll.scroll_end(animate=False)

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        tid = event.item.name or ""
        if tid:
            self._select_thread(tid)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        btn_id = event.button.id or ""
        if btn_id == "btn-dm-refresh":
            event.stop()
            self.refresh_threads()
            self.app.notify("🔄 Xabarlar yangilandi!")
        elif btn_id == "btn-dm-send":
            event.stop()
            self._send_current_message()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "dm-message-input":
            event.stop()
            self._send_current_message()
        elif event.input.id == "dm-new-user-input":
            event.stop()
            self._start_new_chat()

    def _start_new_chat(self) -> None:
        inp = self.query_one("#dm-new-user-input", Input)
        target_user = inp.value.strip().lstrip("@")
        if not target_user:
            return
        thread = self.service.start_direct_thread(target_user)
        inp.value = ""
        self._active_thread_id = thread.id
        self.refresh_threads()
        self.app.notify(f"💬 @{target_user} bilan suhbat ochildi!")

    def _send_current_message(self) -> None:
        if not self._active_thread_id:
            self.app.notify("Avval suhbatni tanlang!", severity="warning")
            return
        inp = self.query_one("#dm-message-input", Input)
        text = inp.value.strip()
        if not text:
            return
        self.service.send_direct_message(self._active_thread_id, text)
        inp.value = ""
        self._select_thread(self._active_thread_id)
        self.app.notify("✉️ Xabar yuborildi!")
