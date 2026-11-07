"""Login Screen for InstaTerminal with live animated loader, Bloks CAA auth, SessionID auth, and Demo Mode."""

from __future__ import annotations

import asyncio
import time
from typing import Optional

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.timer import Timer
from textual.widgets import Button, Input, Label, LoadingIndicator, Static

from instaterminal.core.client import InstaAuthError, InstaClientService

LOGO_ASCII = r"""
 ___           _       _____                   _             _ 
|_ _|_ __  ___| |_ __ |_   _|__ _ __ _ __ ___ (_)_ __   __ _| |
 | || '_ \/ __| __/ _` || |/ _ \ '__| '_ ` _ \| | '_ \ / _` | |
 | || | | \__ \ || (_| || |  __/ |  | | | | | | | | | | (_| | |
|___|_| |_|___/\__\__,_||_|\___|_|  |_| |_| |_|_|_| |_|\__,_|_|
"""

SPINNER_FRAMES = ("⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏")


class LoginScreen(Screen[bool]):
    """Authentication screen with non-blocking Live login, SessionID support, animated spinner, and instant Demo mode."""

    BINDINGS = [
        ("escape", "app.quit", "Chiqish"),
        ("f2", "start_demo", "Demo Rejim"),
    ]

    def __init__(self, service: InstaClientService) -> None:
        super().__init__()
        self.service = service
        self._is_loading: bool = False
        self._load_start_time: float = 0.0
        self._load_message: str = ""
        self._frame_idx: int = 0
        self._spinner_timer: Optional[Timer] = None

    def compose(self) -> ComposeResult:
        with Vertical(id="login-card"):
            yield Static(LOGO_ASCII.strip("\n"), id="login-logo")
            yield Static(
                "Instagram Terminal (TUI) Klienti • instagrapi + Textual",
                id="login-subtitle",
            )

            with Horizontal(id="login-actions"):
                yield Button("🔐 Kirish (Live)", id="btn-login-live", variant="primary")
                if self.service.has_saved_session():
                    yield Button("♻️ Saqlangan Sessiya", id="btn-login-session", variant="warning")
                yield Button("🚀 Demo Rejim (F2)", id="btn-login-demo", variant="success")

            with Vertical(id="login-loader-row"):
                yield LoadingIndicator(id="login-spinner")

            session_hint = (
                "✅ Saqlangan sessiya topildi! '♻️ Saqlangan Sessiya' yoki '🚀 Demo Rejim' ni tanlang."
                if self.service.has_saved_session()
                else "💡 Maslahat: Login/Parol yozib '🔐 Kirish (Live)' bosing yoki '🚀 Demo Rejim (F2)' tanlang."
            )
            yield Static(session_hint, id="login-status")

            yield Label("👤 Instagram Username:", classes="login-label")
            yield Input(
                placeholder="username",
                id="login-username",
            )

            yield Label("🔑 Parol:", classes="login-label")
            yield Input(
                placeholder="Instagram parolingiz",
                password=True,
                id="login-password",
            )

            yield Label("🛡️ 2FA Tasdiqlash kodi (ixtiyoriy):", classes="login-label")
            yield Input(
                placeholder="Agar 2FA yoqilgan bo'lsa, 6 xonali SMS/Auth kod",
                id="login-2fa",
            )

            yield Label("🍪 Yoki Brauzer SessionID (ixtiyoriy — parolsiz kirish):", classes="login-label")
            yield Input(
                placeholder="Brauzer cookie'dagi sessionid qiymati (ixtiyoriy)",
                password=True,
                id="login-sessionid",
            )

    def on_mount(self) -> None:
        self.query_one("#login-username", Input).focus()

    def _start_loading_ui(self, message: str) -> None:
        """Activate visual spinner, elapsed timer, and button loading state."""
        self._is_loading = True
        self._load_start_time = time.monotonic()
        self._load_message = message
        self._frame_idx = 0

        loader_row = self.query_one("#login-loader-row", Vertical)
        loader_row.add_class("active")

        live_btn = self.query_one("#btn-login-live", Button)
        live_btn.label = "⏳ Ulanilmoqda..."
        live_btn.disabled = True

        for btn_id in ("#btn-login-demo", "#btn-login-session"):
            matches = self.query(btn_id)
            for b in matches:
                b.disabled = True

        self._tick_spinner()
        if self._spinner_timer is None:
            self._spinner_timer = self.set_interval(0.15, self._tick_spinner)

    def _stop_loading_ui(self) -> None:
        """Stop visual spinner and restore buttons."""
        self._is_loading = False
        if self._spinner_timer is not None:
            self._spinner_timer.stop()
            self._spinner_timer = None

        loader_row = self.query_one("#login-loader-row", Vertical)
        loader_row.remove_class("active")

        live_btn = self.query_one("#btn-login-live", Button)
        live_btn.label = "🔐 Kirish (Live)"
        live_btn.disabled = False

        for btn_id in ("#btn-login-demo", "#btn-login-session"):
            matches = self.query(btn_id)
            for b in matches:
                b.disabled = False

    def _tick_spinner(self) -> None:
        if not self._is_loading:
            return
        elapsed = time.monotonic() - self._load_start_time
        frame = SPINNER_FRAMES[self._frame_idx % len(SPINNER_FRAMES)]
        self._frame_idx += 1
        status = self.query_one("#login-status", Static)
        status.update(f"{frame} {self._load_message} ({elapsed:.1f}s)")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        btn_id = event.button.id or ""
        if btn_id == "btn-login-demo":
            event.stop()
            self.action_start_demo()
        elif btn_id == "btn-login-session":
            event.stop()
            self.run_worker(self._handle_saved_session_async(), exclusive=True)
        elif btn_id == "btn-login-live":
            event.stop()
            self.run_worker(self._handle_live_login_async(), exclusive=True)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id in ("login-username", "login-password", "login-2fa", "login-sessionid"):
            event.stop()
            if not self._is_loading:
                self.run_worker(self._handle_live_login_async(), exclusive=True)

    def action_start_demo(self) -> None:
        """Activate rich interactive Demo mode immediately."""
        if self._is_loading:
            return
        self._start_loading_ui("🚀 Demo muhit va tasvirlar tayyorlanmoqda...")
        self.service.enable_demo_mode()
        self._stop_loading_ui()
        self.app.notify("🚀 Demo rejim faollashtirildi! Barcha funksiyalar tayyor.")
        self.dismiss(True)

    async def _handle_saved_session_async(self) -> None:
        if self._is_loading:
            return
        status = self.query_one("#login-status", Static)
        self.app.notify("⏳ Saqlangan sessiya orqali ulanilmoqda...")
        self._start_loading_ui("Saqlangan Instagram sessiyasi tekshirilmoqda...")

        ok = await asyncio.to_thread(self.service.load_saved_session)
        self._stop_loading_ui()

        if ok:
            status.update(f"✅ Xush kelibsiz, @{self.service.username}!")
            self.app.notify(f"✅ Xush kelibsiz, @{self.service.username}!")
            self.dismiss(True)
        else:
            msg = "⚠️ Saqlangan sessiya eskirgan. Login/parol kiriting yoki Demo rejimni bosing."
            status.update(msg)
            self.app.notify(msg, severity="warning")

    async def _handle_live_login_async(self) -> None:
        if self._is_loading:
            return

        uname_inp = self.query_one("#login-username", Input)
        pwd_inp = self.query_one("#login-password", Input)
        code_inp = self.query_one("#login-2fa", Input)
        sid_inp = self.query_one("#login-sessionid", Input)
        status = self.query_one("#login-status", Static)

        uname = uname_inp.value.strip()
        pwd = pwd_inp.value
        code = code_inp.value.strip()
        sid = sid_inp.value.strip()

        # If user provided a browser SessionID cookie, authenticate with it directly
        if sid:
            self.app.notify("⏳ SessionID orqali Instagram hisobiga ulanilmoqda...", title="SessionID Login")
            self._start_loading_ui("SessionID cookie orqali ulanilmoqda...")
            try:
                await asyncio.to_thread(self.service.login_with_sessionid, sid)
                self._stop_loading_ui()
                status.update(f"✅ Muvaffaqiyatli kirildi: @{self.service.username}")
                self.app.notify(f"✅ Muvaffaqiyatli kirildi: @{self.service.username}!")
                self.dismiss(True)
            except InstaAuthError as exc:
                self._stop_loading_ui()
                status.update(f"❌ {exc}")
                self.app.notify(str(exc), title="SessionID xatosi", severity="error")
            return

        if not uname:
            msg = "⚠️ Iltimos, avval Instagram Username kiriting (yoki SessionID yozing)!"
            status.update(msg)
            self.app.notify(msg, title="Login kiritilmadi", severity="warning")
            uname_inp.focus()
            return

        if not pwd:
            msg = f"⚠️ @{uname} uchun Instagram parolni kiriting!"
            status.update(msg)
            self.app.notify(msg, title="Parol kiritilmadi", severity="warning")
            pwd_inp.focus()
            return

        self.app.notify(f"⏳ @{uname} hisobiga ulanilmoqda, kuting...", title="Instagram Live")
        self._start_loading_ui(f"Instagram serveriga ulanilmoqda (@{uname})...")

        try:
            await asyncio.to_thread(self.service.login, uname, pwd, code)
            self._stop_loading_ui()
            status.update(f"✅ Muvaffaqiyatli kirildi: @{self.service.username}")
            self.app.notify(
                f"✅ Muvaffaqiyatli kirildi: @{self.service.username}!",
                title="Xush kelibsiz",
            )
            self.dismiss(True)
        except InstaAuthError as exc:
            self._stop_loading_ui()
            status.update(f"❌ {exc}")
            self.app.notify(str(exc), title="Kirishda xatolik", severity="error")
            if exc.requires_2fa:
                code_inp.focus()
        except Exception as exc:
            self._stop_loading_ui()
            status.update(f"❌ Ulanish xatosi: {exc}")
            self.app.notify(f"Xatolik: {exc}", title="Xatolik", severity="error")
