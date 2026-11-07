"""Simple, Fast, 100% Real Terminal CLI for Instagram (InstaTerminal)."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

from rich import box
from rich.columns import Columns
from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text

from instaterminal import __version__
from instaterminal.core.client import InstaAuthError, InstaClientService
from instaterminal.core.config import get_downloads_dir, get_session_file, get_user_download_dir
from instaterminal.core.image_renderer import TerminalImageRenderer
from instaterminal.core.models import HighlightItem, PostItem, UserProfile, UserShort

console = Console()


def render_profile_to_terminal(
    profile: UserProfile,
    show_post_images: bool = False,
) -> None:
    """Print complete real Instagram profile metadata, highlights, and posts to the terminal."""
    console.print()
    console.print(
        Rule(
            f"[bold bright_magenta]📸 INSTAGRAM REAL PROFIL: @{profile.username}[/bold bright_magenta]",
            style="magenta",
        )
    )

    # 1. Render real avatar in terminal if available
    avatar_renderable: Optional[Panel] = None
    if profile.local_avatar_path and profile.local_avatar_path.exists():
        art = TerminalImageRenderer.render_image(
            profile.local_avatar_path,
            width=28,
            max_height=14,
            mode="unicode",
        )
        avatar_renderable = Panel(
            art,
            title=f"[bold cyan]@{profile.username}[/bold cyan]",
            subtitle="[dim]Real Avatar[/dim]",
            border_style="cyan",
            padding=(0, 1),
        )

    # 2. Full Profile Metadata Table (Every field Instagram provides)
    is_narrow = console.size.width < 90
    info_table = Table(
        show_header=False,
        box=box.SIMPLE_HEAVY,
        pad_edge=False,
        expand=True,
    )
    info_table.add_column("Maydon", style="bold cyan", width=18 if is_narrow else 26)
    info_table.add_column("Qiymat", style="white", ratio=1)

    verified_badge = "✅ Tasdiqlangan (Verified)" if profile.is_verified else "Yo'q"
    privacy_badge = "🔒 Yopiq (Private)" if profile.is_private else "🌍 Ochiq (Public)"

    info_table.add_row("👤 Username", f"[bold bright_white]@{profile.username}[/bold bright_white]")
    info_table.add_row("📛 To'liq ismi (Full Name)", profile.full_name or "[dim]Kiritilmagan[/dim]")
    info_table.add_row("🆔 Instagram User ID (PK)", profile.user_id or "[dim]Noma'lum[/dim]")
    if profile.fbid:
        info_table.add_row("🧬 Graph ID (FBID)", profile.fbid)
    info_table.add_row("✔️ Verified holati", verified_badge)
    info_table.add_row("🔐 Maxfiylik (Privacy)", privacy_badge)
    info_table.add_row(
        "📊 Asosiy Statistika",
        (
            f"[bold yellow]{profile.media_count:,}[/bold yellow] Postlar  •  "
            f"[bold green]{profile.follower_count:,}[/bold green] Obunachilar (Followers)  •  "
            f"[bold cyan]{profile.following_count:,}[/bold cyan] Obunalar (Following)"
        ),
    )
    if profile.pronouns:
        info_table.add_row("🗣️ Olmoshlar (Pronouns)", ", ".join(profile.pronouns))

    info_table.add_row(
        "📝 Biografiya (Bio)",
        profile.biography.strip() if profile.biography.strip() else "[dim]Biografiya yozilmagan[/dim]",
    )

    if profile.bio_links:
        info_table.add_row("🔗 Bio Havolalar (Links)", "\n".join(profile.bio_links))
    elif profile.external_url:
        info_table.add_row("🔗 Tashqi Havola", profile.external_url)

    if profile.category_name:
        info_table.add_row("🏷️ Kategoriya", profile.category_name)
    if profile.public_email:
        info_table.add_row("📧 Email", profile.public_email)
    if profile.contact_phone_number:
        info_table.add_row("📞 Telefon", profile.contact_phone_number)

    story_badge = (
        f"🟢 Mavjud ({len(profile.stories)} ta faol 24s Story)"
        if profile.stories
        else ("🟢 Mavjud (Faol)" if profile.has_public_story else "⚪ Yo'q")
    )
    info_table.add_row("⚡ Faol Story (24 soatlik)", story_badge)
    info_table.add_row(
        "🎬 Reels / Clips mavjudligi",
        "🟢 Ha (Reels bor)" if profile.has_any_clips else "⚪ Yo'q",
    )
    if profile.latest_reel_media > 0:
        reel_dt = datetime.fromtimestamp(profile.latest_reel_media).strftime("%Y-%m-%d %H:%M:%S")
        info_table.add_row("🕒 Oxirgi Story vaqti", reel_dt)

    if profile.show_text_post_app_badge or profile.text_post_app_badge_label:
        info_table.add_row(
            "🧵 Threads Nishoni",
            profile.text_post_app_badge_label or "Faol",
        )
    if profile.account_badges:
        info_table.add_row("🏅 Hisob Nishonlari", ", ".join(profile.account_badges))
    if profile.is_memorialized:
        info_table.add_row("🕊️ Xotira hisobi (Memorialized)", "Ha")

    info_table.add_row("🌐 Profil Havolasi", f"[underline bright_blue]{profile.profile_link}[/underline bright_blue]")
    if profile.profile_pic_url:
        short_pic = (
            profile.profile_pic_url[:85] + "..."
            if len(profile.profile_pic_url) > 85
            else profile.profile_pic_url
        )
        info_table.add_row("🖼️ Avatar CDN URL", f"[dim]{short_pic}[/dim]")
    if profile.local_avatar_path:
        info_table.add_row("💾 Keshdagi Avatar Fayli", f"[dim]{profile.local_avatar_path}[/dim]")
    if profile.request_id:
        info_table.add_row("📡 Instagram Request ID", f"[dim]{profile.request_id}[/dim]")

    info_panel = Panel(
        info_table,
        title=f"[bold bright_green]📋 @{profile.username} — To'liq Instagram Ma'lumotlari[/bold bright_green]",
        border_style="green",
    )

    if avatar_renderable is not None:
        if is_narrow:
            console.print(avatar_renderable)
            console.print(info_panel)
        else:
            console.print(Columns([avatar_renderable, info_panel], expand=True))
    else:
        console.print(info_panel)

    # 2b. Active 24h Stories Section
    if profile.stories:
        act_st_table = Table(
            title=f"🔥 Faol 24-soatlik Storylar ({len(profile.stories)} ta)",
            box=box.ROUNDED,
            border_style="bright_magenta",
            expand=True,
        )
        act_st_table.add_column("#", style="bold bright_magenta", width=4)
        act_st_table.add_column("Story ID / Kod", style="cyan", width=24)
        act_st_table.add_column("Format", style="yellow", width=18)
        act_st_table.add_column("Joylangan vaqti", style="green", width=20)
        act_st_table.add_column("Holati", style="white")
        for idx, st in enumerate(profile.stories, start=1):
            fmt = f"🎬 Video MP4 ({st.video_duration:.1f}s)" if st.media_type == "video" else "📸 Photo HD"
            act_st_table.add_row(
                str(idx),
                f"{st.code} ({st.id})",
                fmt,
                st.taken_at,
                "⬇️ Yuklab olish tayyor ([bold yellow]st save[/bold yellow])",
            )
        console.print(act_st_table)

    # 3. Story Highlights Section
    if profile.highlights:
        hl_table = Table(
            title=f"✨ Story Highlights ({len(profile.highlights)} ta)",
            box=box.ROUNDED,
            border_style="yellow",
            expand=True,
        )
        hl_table.add_column("#", style="bold yellow", width=4)
        hl_table.add_column("Highlight ID", style="cyan", width=20)
        hl_table.add_column("Sarlavha (Title)", style="bold white", width=24)
        hl_table.add_column("Storylar Soni", style="bold green", width=15)
        hl_table.add_column("Yaratilgan Sana", style="magenta", width=14)
        hl_table.add_column("Muqova URL (Cover)", style="dim")

        for idx, hl in enumerate(profile.highlights, start=1):
            cover_short = (
                (hl.cover_url[:50] + "...") if hl.cover_url and len(hl.cover_url) > 50 else (hl.cover_url or "-")
            )
            cnt_str = f"{hl.media_count} ta story" if hl.media_count > 0 else "Mavjud"
            pin_tag = " 📌" if hl.is_pinned else ""
            hl_table.add_row(
                str(idx),
                hl.id,
                f"{hl.title}{pin_tag}",
                cnt_str,
                hl.created_at or "-",
                cover_short,
            )
        console.print(hl_table)
        console.print(
            "[dim]💡 Highlight storylariga kirish: [bold yellow]hl 1[/bold yellow] | "
            "Yuklab olish: [bold yellow]hl save 1[/bold yellow] | "
            "Barchasini yuklash: [bold yellow]hl save all[/bold yellow] | "
            "Obunachilar: [bold yellow]followers[/bold yellow] | "
            "Obunalar: [bold yellow]following[/bold yellow][/dim]"
        )

    # 4. Posts & Reels Section
    if not profile.posts:
        if profile.is_private:
            console.print(
                Panel(
                    f"🔒 [bold yellow]@{profile.username}[/bold yellow] yopiq (Private) profil. "
                    f"Jami postlar soni: [bold]{profile.media_count}[/bold].",
                    border_style="yellow",
                )
            )
        else:
            console.print(
                Panel(
                    f"📭 [bold cyan]@{profile.username}[/bold cyan] profilida hozircha joylangan postlar yo'q "
                    f"(Postlar soni: [bold]{profile.media_count}[/bold]).",
                    border_style="cyan",
                )
            )
    else:
        posts_table = Table(
            title=(
                f"📸 Oxirgi Joylangan Postlar va Reels "
                f"(Ko'rsatilmoqda: {len(profile.posts)} ta / Jami: {profile.media_count:,} ta)"
            ),
            box=box.ROUNDED,
            border_style="bright_blue",
            show_lines=True,
            expand=True,
        )
        posts_table.add_column("#", style="bold bright_yellow", width=3, justify="right")
        posts_table.add_column("Kod / Tur", style="cyan", width=15)
        posts_table.add_column("Vaqt / Joy", style="green", width=16)
        posts_table.add_column("Statistika", style="bold bright_red", width=14)
        posts_table.add_column("Matn (Caption) va Tafsilotlar", style="white", ratio=1)

        for idx, p in enumerate(profile.posts, start=1):
            type_icon = {
                "photo": "📸 Photo",
                "video": "🎬 Video",
                "carousel": "🗂️ Album",
            }.get(p.media_type, "📸 Post")
            if p.product_type == "clips":
                type_icon = "🎬 Reel"
            dim_line = f"\n[dim]{p.dimensions}[/dim]" if p.dimensions else ""
            code_col = f"[bold]{p.code}[/bold]\n[magenta]{type_icon}[/magenta]{dim_line}"

            loc_str = f"\n📍 {p.location}" if p.location else ""
            pinned_str = "\n📌 Pinned" if p.is_pinned else ""
            time_col = f"{p.created_at}{loc_str}{pinned_str}"

            if p.likes_hidden:
                stats_col = f"❤️ Yashirilgan\n💬 {p.comment_count:,}"
            elif p.like_count > 0 or p.comment_count > 0 or p.play_count > 0:
                play_str = f"\n▶️ {p.play_count:,}" if p.play_count > 0 else ""
                stats_col = f"❤️ {p.like_count:,}\n💬 {p.comment_count:,}{play_str}"
            else:
                stats_col = "❤️ 0\n💬 0"

            details_parts: list[str] = [f"[dim]ID: {p.id}[/dim]"]
            if p.resources:
                details_parts.append(f"[bold yellow]🗂️ Albom ichida {len(p.resources)} ta media fayl bor[/bold yellow]")
            if p.caption:
                clean_cap = p.caption.strip()
                if len(clean_cap) > 260:
                    clean_cap = clean_cap[:260] + "..."
                details_parts.append(clean_cap)
            if p.accessibility_caption:
                details_parts.append(f"[dim italic]🤖 AI: {p.accessibility_caption}[/dim italic]")
            if p.coauthors:
                details_parts.append(f"[cyan]🤝 {', '.join('@' + c for c in p.coauthors)}[/cyan]")
            if p.is_paid_partnership:
                details_parts.append("[yellow]💼 Paid Partnership[/yellow]")
            details_parts.append(f"[underline bright_blue]{p.post_url}[/underline bright_blue]")

            posts_table.add_row(
                str(idx),
                code_col,
                time_col,
                stats_col,
                "\n".join(details_parts),
            )

        console.print(posts_table)

        if show_post_images:
            render_posts_images_to_terminal(profile)

    # 5. Always Render Download Center Panel
    render_download_center_panel(profile)


def render_download_center_panel(profile: UserProfile) -> None:
    """Display a summary panel of everything available to download on the profile."""
    total_hl_stories = sum(h.media_count for h in profile.highlights)
    hl_info = (
        f"{len(profile.highlights)} ta Highlight ({total_hl_stories} ta story)"
        if total_hl_stories > 0
        else f"{len(profile.highlights)} ta Highlight"
    )
    dl_table = Table(show_header=True, box=box.SIMPLE_HEAVY, expand=True)
    dl_table.add_column("Yuklab olinadigan ma'lumot", style="bold white", ratio=2)
    dl_table.add_column("Mavjud miqdor", style="bright_cyan", ratio=2)
    dl_table.add_column("Terminal Buyrug'i", style="bold bright_yellow", ratio=2)

    user_dl_dir = get_downloads_dir() / f"@{profile.username}"
    dl_table.add_row(
        "🚀 BARCHASINI BIRDANIGA YUKLAB OLISH",
        "Avatar + Story + HL + Post + Info",
        "[bold bright_green]save all[/bold bright_green]  (yoki [bold bright_green]all[/bold bright_green])",
    )
    dl_table.add_row(
        "🖼️ Profil Avatari (@user/avatar/)",
        "1 ta HD rasm" if profile.profile_pic_url else "Mavjud emas",
        "save avatar",
    )
    dl_table.add_row(
        "🔥 Faol 24s Storylar (@user/story/)",
        f"{len(profile.stories)} ta faol story",
        "st save  (yoki save st)",
    )
    dl_table.add_row(
        "✨ Story Highlights (@user/highlight/)",
        hl_info,
        "hl save all  (yoki hl save 1)",
    )
    dl_table.add_row(
        "📸 Postlar va Reels (@user/posts | reels/)",
        f"{profile.media_count:,} ta post/reel",
        "save posts  (yoki save 1, save reels)",
    )
    dl_table.add_row(
        "👥 Obunachilar/Obunalar (@user/followers/)",
        f"{profile.follower_count:,} obunachi / {profile.following_count:,} obuna",
        "save followers  |  save following",
    )
    dl_table.add_row(
        "📋 Profil Ma'lumotlari (@user/info/)",
        "To'liq hisobot + JSON",
        "save info",
    )
    dl_table.add_row(
        "📂 Profilning shaxsiy papkasi",
        str(user_dl_dir),
        "folder  (papkani ochish)",
    )

    console.print(
        Panel(
            dl_table,
            title=f"[bold bright_green]⬇️ @{profile.username} — YUKLAB OLISH MARKAZI (Download Center)[/bold bright_green]",
            border_style="bright_green",
        )
    )


def render_download_everything_summary(
    username: str,
    results: dict[str, list[Path]],
) -> None:
    """Display a clean summary table of all files downloaded by download_everything_for_profile."""
    total_files = sum(len(v) for v in results.values())
    base_dir = get_downloads_dir() / f"@{username}"

    sum_table = Table(
        title=f"✅ @{username} — BARCHA MA'LUMOTLAR YUKLAB OLINDI (Jami: {total_files} ta fayl)",
        box=box.ROUNDED,
        border_style="bright_green",
        expand=True,
    )
    sum_table.add_column("Bo'lim (Kategoriya)", style="bold cyan", width=30)
    sum_table.add_column("Yuklangan fayllar", style="bold yellow", width=18, justify="right")
    sum_table.add_column("Saqlangan joyi (Papka / Fayl)", style="white")

    labels = {
        "avatar": "🖼️ Full HD Avatar",
        "stories_24h": "🔥 Faol 24-soatlik Storylar",
        "highlights": "✨ Story Highlights (Video/Rasm)",
        "posts_and_reels": "📸 Postlar, Reels va Albomlar",
        "followers_following": "👥 Obunachilar va Obunalar (.txt/.json)",
        "info": "📋 Profil Ma'lumotlari (.txt/.json)",
    }

    for key, label in labels.items():
        files = results.get(key) or []
        if files:
            loc = str(files[0].parent) if len(files) > 1 else str(files[0])
            sum_table.add_row(label, f"{len(files)} ta fayl", f"[underline cyan]{loc}[/underline cyan]")
        else:
            sum_table.add_row(label, "[dim]0 ta[/dim]", "[dim]Mavjud emas[/dim]")

    console.print()
    console.print(sum_table)
    console.print(
        Panel(
            f"📁 Barcha fayllar ushbu papkaga tartibli saqlandi:\n"
            f"[bold underline bright_cyan]{base_dir}[/bold underline bright_cyan]\n"
            f"[dim]💡 Papkani Windows Explorer'da darhol ochish uchun [bold yellow]folder[/bold yellow] deb yozing.[/dim]",
            border_style="bright_green",
        )
    )


def render_single_post_detail(profile: UserProfile, index: int) -> None:
    """Render full details and terminal image preview for post #index (1-based)."""
    if index < 1 or index > len(profile.posts):
        console.print(
            f"[bold red]❌ Noto'g'ri post raqami: {index}. "
            f"Mavjud postlar: 1..{len(profile.posts)}[/bold red]"
        )
        return

    post: PostItem = profile.posts[index - 1]
    console.print()
    console.print(
        Rule(
            f"[bold cyan]📸 POST #{index} — @{post.username} ({post.code})[/bold cyan]",
            style="cyan",
        )
    )

    if post.local_image_path and post.local_image_path.exists():
        img_art = TerminalImageRenderer.render_image(
            post.local_image_path,
            width=64,
            max_height=28,
            mode="unicode",
        )
        console.print(
            Panel(
                img_art,
                title=f"[bold bright_white]@{post.username} • {post.code}[/bold bright_white]",
                subtitle=f"[dim]{post.local_image_path}[/dim]",
                border_style="bright_magenta",
            )
        )

    meta = Table(show_header=False, box=box.SIMPLE, expand=True)
    meta.add_column("Key", style="bold cyan", width=24)
    meta.add_column("Val", style="white")
    meta.add_row("🆔 Post ID (PK)", post.id)
    meta.add_row("🔑 Shortcode", post.code)
    meta.add_row("📦 Media Turi", f"{post.media_type} ({post.typename or post.product_type})")
    if post.dimensions:
        meta.add_row("📐 O'lchamlari", post.dimensions)
    meta.add_row("🕒 Joylangan vaqti", post.created_at)
    meta.add_row("❤️ Layklar soni", "Yashirilgan" if post.likes_hidden else f"{post.like_count:,}")
    meta.add_row("💬 Izohlar soni", f"{post.comment_count:,}")
    if post.location:
        meta.add_row("📍 Joylashuv", post.location)
    if post.coauthors:
        meta.add_row("🤝 Hammualliflar", ", ".join(f"@{c}" for c in post.coauthors))
    meta.add_row("📝 To'liq Caption", post.caption or "[dim]Matn yo'q[/dim]")
    if post.accessibility_caption:
        meta.add_row("🤖 AI Tavsifi", post.accessibility_caption)
    meta.add_row("🔗 Post Havolasi", post.post_url)
    if post.image_url:
        meta.add_row("🖼️ Rasm CDN URL", f"[dim]{post.image_url}[/dim]")

    console.print(Panel(meta, title="[bold green]Post Tafsilotlari[/bold green]", border_style="green"))


def render_posts_images_to_terminal(profile: UserProfile, limit: int = 6) -> None:
    """Render terminal Unicode previews for the latest posts of the profile."""
    if not profile.posts:
        console.print("[yellow]Postlar mavjud emas.[/yellow]")
        return

    panels: list[Panel] = []
    for idx, p in enumerate(profile.posts[:limit], start=1):
        if p.local_image_path and p.local_image_path.exists():
            art = TerminalImageRenderer.render_image(
                p.local_image_path,
                width=36,
                max_height=16,
                mode="unicode",
            )
            panels.append(
                Panel(
                    art,
                    title=f"[bold yellow]#{idx}[/bold yellow] [cyan]{p.code}[/cyan]",
                    subtitle=f"❤️ {p.like_count:,}  💬 {p.comment_count:,}",
                    border_style="blue",
                )
            )
    if panels:
        console.print(Columns(panels, equal=False, expand=False))


def render_highlight_stories_to_terminal(highlight: HighlightItem) -> None:
    """Display all real Story items inside a Highlight with terminal previews and download options."""
    console.print()
    console.print(
        Rule(
            f"[bold bright_yellow]✨ HIGHLIGHT STORYLAR: {highlight.title} "
            f"(@{highlight.owner_username} • ID: {highlight.id})[/bold bright_yellow]",
            style="yellow",
        )
    )

    if not highlight.items:
        console.print("[yellow]Ushbu Highlight ichida storylar topilmadi.[/yellow]")
        return

    st_table = Table(
        title=f"🎬 Highlight: '{highlight.title}' — Jami {len(highlight.items)} ta Story",
        box=box.ROUNDED,
        border_style="bright_yellow",
        show_lines=True,
        expand=True,
    )
    st_table.add_column("#", style="bold yellow", width=3, justify="right")
    st_table.add_column("Story ID / Kod", style="cyan", width=22)
    st_table.add_column("Turi / Format", style="magenta", width=18)
    st_table.add_column("Joylangan vaqt", style="green", width=19)
    st_table.add_column("Tafsilotlar va Yuklab olish", style="white", ratio=1)

    for idx, s in enumerate(highlight.items, start=1):
        if s.media_type == "video":
            dur_str = f" ({s.video_duration:.1f}s)" if s.video_duration > 0 else ""
            audio_str = " 🔊" if s.has_audio else ""
            type_col = f"🎬 Video MP4{dur_str}{audio_str}\n[dim]{s.dimensions}[/dim]"
        else:
            type_col = f"📸 Photo HD\n[dim]{s.dimensions}[/dim]"

        details: list[str] = []
        if s.caption:
            details.append(s.caption)
        if s.accessibility_caption:
            details.append(f"[dim italic]🤖 AI: {s.accessibility_caption}[/dim italic]")
        if s.video_url:
            details.append("[bright_green]⬇️ Full HD MP4 video yuklab olishga tayyor[/bright_green]")
        elif s.image_url:
            details.append("[bright_cyan]⬇️ Full HD JPG rasm yuklab olishga tayyor[/bright_cyan]")

        st_table.add_row(
            str(idx),
            f"[bold]{s.code or s.id}[/bold]\n[dim]{s.id}[/dim]",
            type_col,
            s.taken_at,
            "\n".join(details),
        )

    console.print(st_table)

    # Render terminal image previews of the stories
    panels: list[Panel] = []
    for idx, s in enumerate(highlight.items[:6], start=1):
        if s.local_image_path and s.local_image_path.exists():
            art = TerminalImageRenderer.render_image(
                s.local_image_path,
                width=28,
                max_height=14,
                mode="unicode",
            )
            tag = "🎬 MP4" if s.media_type == "video" else "📸 JPG"
            panels.append(
                Panel(
                    art,
                    title=f"[bold yellow]Story #{idx}[/bold yellow] ({tag})",
                    subtitle=f"[dim]{s.taken_at.split()[0]}[/dim]",
                    border_style="yellow",
                )
            )
    if panels:
        console.print(Columns(panels, equal=False, expand=False))


def open_highlight_interactive(
    service: InstaClientService,
    highlight: HighlightItem,
) -> None:
    """Interactive Highlight viewer allowing one-click download of any or all stories."""
    render_highlight_stories_to_terminal(highlight)
    if not highlight.items:
        return

    console.print(
        Panel(
            "[bold yellow]⬇️ HIGHLIGHT YUKLAB OLISH MENYUSI:[/bold yellow]\n"
            "  • [bold bright_green]all[/bold bright_green] (yoki [bold bright_green]a[/bold bright_green])      — Barcha storylarni (MP4 video + JPG rasm) yuklab olish\n"
            "  • [bold bright_cyan]1[/bold bright_cyan], [bold bright_cyan]2[/bold bright_cyan], ...       — Shu raqamdagi storyni yuklab olish (masalan: [bold]1[/bold] yoki [bold]save 2[/bold])\n"
            "  • [bold bright_magenta]open 1[/bold bright_magenta]          — Shu raqamdagi storyni yuklab olib Windows pleyerida ochish\n"
            "  • [bold white]Enter[/bold white] yoki [bold red]b[/bold red]    — Profilga qaytish",
            border_style="yellow",
        )
    )

    while True:
        try:
            sub_cmd = console.input(
                f"[bold yellow]highlight[/bold yellow] ([cyan]{highlight.title}[/cyan] • 1..{len(highlight.items)}) [bold green]>[/bold green] "
            ).strip()
        except (EOFError, KeyboardInterrupt):
            console.print()
            break

        if not sub_cmd or sub_cmd.lower() in ("b", "back", "q", "exit"):
            break

        sparts = sub_cmd.split()
        scmd = sparts[0].lower()
        sarg = " ".join(sparts[1:]).strip()

        if scmd in ("all", "a", "saveall") or (scmd == "save" and sarg.lower() == "all"):
            with console.status(
                f"[bold green]⬇️ '{highlight.title}' ichidagi barcha {len(highlight.items)} ta story yuklab olinmoqda...[/bold green]",
                spinner="dots",
            ):
                saved_paths = service.download_all_highlight_stories(highlight)
            console.print(
                f"[bold bright_green]✅ Jami {len(saved_paths)} ta story yuklab olindi![/bold bright_green]"
            )
            for p in saved_paths:
                console.print(f"   📁 [underline cyan]{p}[/underline cyan]")
            continue

        if scmd == "open" and sarg.isdigit():
            idx = int(sarg)
            if 1 <= idx <= len(highlight.items):
                target_story = highlight.items[idx - 1]
                with console.status(
                    f"[bold cyan]⬇️ Story #{idx} ({target_story.media_type.upper()}) yuklab olinmoqda va ochilmoqda...[/bold cyan]",
                    spinner="dots",
                ):
                    saved = service.download_story_item(
                        target_story,
                        highlight_id=highlight.id,
                        highlight_title=highlight.title,
                        owner_username=highlight.owner_username,
                    )
                if saved:
                    service.open_in_system_viewer(saved)
                    console.print(f"[bold green]▶️ Story #{idx} ochildi va saqlandi: {saved}[/bold green]")
                else:
                    console.print("[red]❌ Story faylini yuklab bo'lmadi.[/red]")
            else:
                console.print(f"[red]❌ Story #{idx} topilmadi (1..{len(highlight.items)}).[/red]")
            continue

        # Number directly ("1", "2") or "save 1"
        target_num_str = sarg if (scmd in ("save", "s", "d", "download") and sarg.isdigit()) else scmd
        if target_num_str.isdigit():
            idx = int(target_num_str)
            if 1 <= idx <= len(highlight.items):
                target_story = highlight.items[idx - 1]
                with console.status(
                    f"[bold green]⬇️ Story #{idx} ({target_story.media_type.upper()}) yuklab olinmoqda...[/bold green]",
                    spinner="dots",
                ):
                    saved = service.download_story_item(
                        target_story,
                        highlight_id=highlight.id,
                        highlight_title=highlight.title,
                        owner_username=highlight.owner_username,
                    )
                if saved:
                    console.print(f"[bold bright_green]✅ Story #{idx} saqlandi: {saved}[/bold bright_green]")
                else:
                    console.print("[red]❌ Story faylini yuklab bo'lmadi.[/red]")
            else:
                console.print(f"[red]❌ Story #{idx} topilmadi (1..{len(highlight.items)}).[/red]")
            continue

        console.print(
            "[yellow]💡 Story raqamini yozing (masalan: 1), barchasini yuklash uchun 'all', chiqish uchun Enter bosing.[/yellow]"
        )


def render_user_list_to_terminal(
    title: str,
    users: list[UserShort],
    total_count: int = 0,
) -> None:
    """Render a table of followers or following users."""
    console.print()
    console.print(
        Rule(
            f"[bold bright_cyan]👥 {title} ({len(users)} ta ko'rsatilmoqda / Jami: {total_count:,} ta)[/bold bright_cyan]",
            style="cyan",
        )
    )

    if not users:
        console.print("[yellow]Foydalanuvchilar ro'yxati bo'sh yoki olinmadi.[/yellow]")
        return

    is_narrow = console.size.width < 90
    table = Table(
        box=box.ROUNDED,
        border_style="cyan",
        show_lines=True,
        expand=True,
    )
    table.add_column("#", style="bold yellow", width=4, justify="right")
    table.add_column("Username", style="bold bright_white", ratio=2)
    table.add_column("To'liq ismi", style="white", ratio=2)
    table.add_column("Holati", style="magenta", ratio=1)
    if not is_narrow:
        table.add_column("Instagram Havolasi", style="dim", ratio=2)

    for idx, u in enumerate(users, start=1):
        v_tag = "✅ Verified" if u.is_verified else ""
        p_tag = "🔒 Yopiq" if u.is_private else "🌍 Ochiq"
        status_str = f"{p_tag}  {v_tag}".strip()
        link_str = f"https://www.instagram.com/{u.username}/"

        row_cells = [
            str(idx),
            f"@{u.username}",
            u.full_name or "[dim]-[/dim]",
            status_str,
        ]
        if not is_narrow:
            row_cells.append(f"[underline blue]{link_str}[/underline blue]")
        table.add_row(*row_cells)

    console.print(table)
    console.print(
        "[dim]💡 Ro'yxatdagi foydalanuvchi profiliga o'tish uchun [bold yellow]u 1[/bold yellow] (raqami) "
        f"yoki [bold yellow]@{users[0].username}[/bold yellow] deb yozing.[/dim]"
    )


def print_help() -> None:
    """Display interactive CLI commands."""
    help_table = Table(
        title="⌨️ InstaTerminal — Terminal Buyruqlari va Yuklab Olish Markazi",
        box=box.ROUNDED,
        border_style="cyan",
    )
    help_table.add_column("Buyruq", style="bold yellow", width=30)
    help_table.add_column("Tavsifi", style="white")
    help_table.add_row("<username> yoki @username", "Istalgan Instagram profilni qidirish va barcha real ma'lumotlarini chiqarish")
    help_table.add_row("save all (yoki all / dl all)", "🚀 PROFILNING HAMMA NARSASINI (Avatar + Story + HL + Post/Reel + Followers + Info) yuklab olish")
    help_table.add_row("save avatar", "🖼️ Profilning Full HD avatarini yuklab olish")
    help_table.add_row("st (yoki st save / save st)", "🔥 Faol 24-soatlik Storylarni ko'rish va barchasini yuklab olish")
    help_table.add_row("hl <N> (masalan: hl 1)", "✨ N-Highlight ichiga kirish va storylarini tanlab yuklab olish")
    help_table.add_row("hl save <N>", "✨ N-Highlight ichidagi barcha storylarni darhol yuklab olish")
    help_table.add_row("hl save all (yoki save hl)", "✨ Profilning BARCHA Highlightlarini (muqova + storylari bilan) yuklab olish")
    help_table.add_row("save <N> (masalan: save 1)", "📸 N-post, Reel yoki Albomning barcha slaydlarini yuklab olish")
    help_table.add_row("save posts (yoki save reels)", "📸 Profilning BARCHA postlari, Reels videolari va Albomlarini yuklab olish")
    help_table.add_row("followers (yoki f)", "👥 Joriy profilning barcha obunachilarini (followers) terminalda ko'rish")
    help_table.add_row("following (yoki fol)", "👥 Joriy profilning barcha obunalarini (following) terminalda ko'rish")
    help_table.add_row("save followers / save following", "💾 Obunachilar yoki obunalar ro'yxatini .txt va .json faylga saqlash")
    help_table.add_row("save info", "📋 Profil haqidagi to'liq hisobotni (.txt va .json) faylga saqlash")
    help_table.add_row("dl <URL>", "🔗 Istalgan Instagram Post/Reel/Highlight/Story havolasini (URL) yuklab olish")
    help_table.add_row("folder (yoki open folder)", "📂 Yuklab olingan fayllar papkasini Windows Explorer'da ochish")
    help_table.add_row("post <N> / open <N>", "🔍 N-post tafsilotlarini ko'rish yoki tizim pleyerida ochish")
    help_table.add_row("images yoki img", "🖼️ Joriy profil postlarining rasmlarini terminalda chizish")
    help_table.add_row("me", "👤 Saqlangan shaxsiy profilingizni ko'rsatish")
    help_table.add_row("login / logout", "🔐 Instagram akkauntga kirish (sessiyani saqlash) yoki chiqish")
    help_table.add_row("update", "🔄 GitHub'dan eng oxirgi yangilanishlarni tortib olish (sessiya saqlanib qoladi)")
    help_table.add_row("json", "🧬 Instagram qaytargan barcha xom (raw) JSON ma'lumotlarni ko'rish")
    help_table.add_row("clear / cls", "🧹 Terminal ekranini tozalash")
    help_table.add_row("q / exit", "🚪 Dasturdan chiqish")
    console.print(help_table)


def run_self_update() -> None:
    """Pull latest updates from GitHub repository without losing saved session."""
    repo_root = Path(__file__).resolve().parent.parent
    console.print("[bold cyan]🔄 GitHub'dan yangilanishlar tekshirilmoqda (git pull)...[/bold cyan]")
    try:
        res = subprocess.run(
            ["git", "-C", str(repo_root), "pull", "origin", "main"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        out = (res.stdout or "").strip()
        err = (res.stderr or "").strip()
        if res.returncode == 0:
            console.print(f"[bold bright_green]✅ InstaTerminal yangilandi![/bold bright_green]\n[dim]{out}[/dim]")
        else:
            console.print(f"[bold red]❌ Yangilashda xatolik:[/bold red] {err or out}")
    except Exception as exc:
        console.print(f"[bold red]❌ Yangilashda xatolik: {exc}[/bold red]")


def prompt_terminal_login(service: InstaClientService) -> bool:
    """
    Interactive one-time terminal login prompt.
    Saves session to ~/.instaterminal/session.json so subsequent launches never ask again.
    """
    console.print()
    console.print(
        Panel(
            "[bold bright_cyan]🔐 INSTAGRAM KIRISH (Bir martalik)[/bold bright_cyan]\n"
            "[white]Kirganingizdan so'ng sessiya avtomatik xotirada saqlanadi "
            f"([cyan]{get_session_file()}[/cyan]) va keyingi safar qayta login/parol so'ramaydi![/white]\n"
            "[dim]💡 Agar parol o'rniga brauzer cookie'dagi sessionid orqali kirmoqchi bo'lsangiz, "
            "Username o'rniga 'sid' deb yozing.[/dim]",
            border_style="bright_cyan",
        )
    )

    while True:
        try:
            raw_user = console.input("[bold yellow]👤 Instagram Username[/bold yellow] (yoki [cyan]sid[/cyan]): ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print()
            return False

        if not raw_user or raw_user.lower() in ("q", "quit", "exit"):
            return False

        if raw_user.lower() in ("sid", "sessionid", "cookie"):
            try:
                sid_val = console.input("[bold yellow]🍪 Instagram sessionid qiymati[/bold yellow]: ").strip()
            except (EOFError, KeyboardInterrupt):
                console.print()
                return False
            if not sid_val:
                continue
            try:
                with console.status("[bold green]🔄 SessionID tekshirilmoqda va saqlanmoqda...[/bold green]", spinner="dots"):
                    service.login(sessionid=sid_val)
                console.print(
                    f"[bold bright_green]✅ Muvaffaqiyatli kirildi: @{service.username}! "
                    "Sessiya saqlandi — endi qayta so'ramaydi.[/bold bright_green]"
                )
                return True
            except Exception as exc:
                console.print(f"[bold red]❌ {exc}[/bold red]")
                continue

        try:
            raw_pass = console.input(
                f"[bold yellow]🔑 @{service.normalize_username(raw_user)} uchun Parol[/bold yellow]: ",
                password=True,
            ).strip()
        except (EOFError, KeyboardInterrupt):
            console.print()
            return False

        if not raw_pass:
            console.print("[yellow]Parol bo'sh bo'lishi mumkin emas.[/yellow]")
            continue

        try:
            with console.status(
                f"[bold cyan]🔐 @{service.normalize_username(raw_user)} akkauntiga kirilmoqda va sessiya saqlanmoqda...[/bold cyan]",
                spinner="dots",
            ):
                service.login(username=raw_user, password=raw_pass)
            console.print(
                f"[bold bright_green]✅ Muvaffaqiyatli kirildi: @{service.username}! "
                "Sessiya saqlandi — keyingi safar login/parol so'ramaydi.[/bold bright_green]"
            )
            return True
        except InstaAuthError as auth_err:
            if auth_err.requires_2fa:
                console.print(f"[bold yellow]🛡️ {auth_err}[/bold yellow]")
                try:
                    code_2fa = console.input("[bold cyan]🔢 6 xonali 2FA tasdiqlash kodi[/bold cyan]: ").strip()
                except (EOFError, KeyboardInterrupt):
                    console.print()
                    return False
                try:
                    with console.status("[bold green]🔐 2FA kod tekshirilmoqda...[/bold green]", spinner="dots"):
                        service.login(
                            username=raw_user,
                            password=raw_pass,
                            verification_code=code_2fa,
                        )
                    console.print(
                        f"[bold bright_green]✅ Muvaffaqiyatli kirildi: @{service.username}! "
                        "Sessiya saqlandi — keyingi safar login/parol so'ramaydi.[/bold bright_green]"
                    )
                    return True
                except Exception as exc2:
                    console.print(f"[bold red]❌ 2FA xatolik: {exc2}[/bold red]")
            else:
                console.print(f"[bold red]❌ {auth_err}[/bold red]")
        except Exception as exc:
            console.print(f"[bold red]❌ Kirishda xatolik: {exc}[/bold red]")


def run_interactive_loop(
    service: InstaClientService,
    initial_username: Optional[str] = None,
    show_images: bool = False,
) -> None:
    """Run the classic terminal REPL for searching and inspecting real Instagram profiles."""
    if not service.authenticated:
        prompt_terminal_login(service)

    session_badge = (
        f"[bold green]@{service.username}[/bold green] (Saqlangan)"
        if service.username
        else "[yellow]Kirish uchun 'login' deb yozing[/yellow]"
    )
    console.print(
        Panel(
            Text.from_markup(
                f"[bold bright_magenta]📸 InstaTerminal v{__version__}[/bold bright_magenta] — "
                f"[bold white]100% Real Instagram Terminal Client & Downloader[/bold white]\n"
                f"🟢 Faol sessiya: {session_badge}  •  "
                f"Istalgan [bold yellow]@username[/bold yellow] yozing | "
                f"Barchasini yuklash: [bold bright_green]save all[/bold bright_green] | "
                f"Yordam: [bold cyan]help[/bold cyan]"
            ),
            border_style="bright_magenta",
        )
    )

    current_profile: Optional[UserProfile] = None
    last_user_list: list[UserShort] = []
    target_start = initial_username or service.username
    if target_start:
        try:
            with console.status(
                f"[bold cyan]🔍 Instagramdan @{service.normalize_username(target_start)} real ma'lumotlari yuklanmoqda...[/bold cyan]",
                spinner="dots",
            ):
                current_profile = service.fetch_real_profile(target_start)
            render_profile_to_terminal(current_profile, show_post_images=show_images)
        except Exception as exc:
            console.print(f"[bold red]❌ Xatolik: {exc}[/bold red]")

    while True:
        try:
            active_tag = f"@{current_profile.username}" if current_profile else f"@{service.username}"
            raw_cmd = console.input(
                f"\n[bold bright_magenta]insta[/bold bright_magenta] ([cyan]{active_tag}[/cyan]) [bold yellow]>[/bold yellow] "
            ).strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]👋 Xayr![/dim]")
            break

        if not raw_cmd:
            continue

        parts = raw_cmd.split()
        cmd = parts[0].lower()
        arg = " ".join(parts[1:]).strip()

        if cmd in ("q", "quit", "exit"):
            console.print("[dim]👋 InstaTerminal yopildi.[/dim]")
            break

        if cmd in ("help", "?", "h"):
            print_help()
            continue

        if cmd in ("clear", "cls"):
            console.clear()
            continue

        if cmd == "update":
            run_self_update()
            continue

        if cmd == "login":
            if prompt_terminal_login(service) and service.username:
                try:
                    with console.status(
                        f"[bold cyan]🔍 @{service.username} profili yuklanmoqda...[/bold cyan]",
                        spinner="dots",
                    ):
                        current_profile = service.fetch_real_profile(service.username)
                    render_profile_to_terminal(current_profile, show_post_images=show_images)
                except Exception:
                    pass
            continue

        if cmd == "logout":
            service.logout()
            current_profile = None
            console.print("[bold yellow]🔓 Sessiya o'chirildi. Qayta kirish uchun 'login' deb yozing.[/bold yellow]")
            continue

        if cmd in ("folder", "downloads", "dir") or (cmd == "open" and arg.lower() in ("folder", "downloads", "dir")):
            dl_dir = get_downloads_dir()
            if current_profile and (dl_dir / f"@{current_profile.username}").exists():
                dl_dir = dl_dir / f"@{current_profile.username}"
            service.open_in_system_viewer(dl_dir)
            console.print(f"[bold green]📂 Yuklab olinganlar papkasi ochildi: {dl_dir}[/bold green]")
            continue

        # Direct Instagram media URL pasted at the prompt (/p/, /reel/, /stories/)
        if any(
            token in raw_cmd
            for token in (
                "instagram.com/p/",
                "instagram.com/reel/",
                "instagram.com/reels/",
                "instagram.com/tv/",
                "instagram.com/stories/",
            )
        ):
            target_url = arg if cmd in ("dl", "download", "save", "s") and arg else raw_cmd
            try:
                with console.status(
                    f"[bold green]⬇️ Instagram havolasidan media yuklab olinmoqda...[/bold green]",
                    spinner="dots",
                ):
                    saved_list = service.download_by_url_or_shortcode(target_url)
                console.print(
                    f"[bold bright_green]✅ Havoladan jami {len(saved_list)} ta fayl yuklab olindi![/bold bright_green]"
                )
                for sp in saved_list:
                    console.print(f"   📁 [underline cyan]{sp}[/underline cyan]")
            except Exception as exc:
                console.print(f"[bold red]❌ Havolani yuklashda xatolik: {exc}[/bold red]")
            continue

        if cmd in ("u", "user") and arg.isdigit() and last_user_list:
            idx_u = int(arg)
            if 1 <= idx_u <= len(last_user_list):
                raw_cmd = last_user_list[idx_u - 1].username
                cmd = raw_cmd.lower()
                arg = ""
            else:
                console.print(f"[red]❌ Ro'yxatda #{idx_u} topilmadi (1..{len(last_user_list)}).[/red]")
                continue

        if cmd == "me":
            raw_cmd = service.username
            cmd = raw_cmd.lower()

        if cmd in ("all", "saveall", "dlall"):
            cmd = "save"
            arg = "all"

        if cmd in ("dl", "download") and not arg:
            if current_profile:
                render_download_center_panel(current_profile)
            else:
                print_help()
            continue

        if cmd in ("dl", "download") and arg:
            cmd = "save"

        if cmd in ("followers", "follower", "f"):
            if not current_profile:
                console.print("[yellow]Avval biror username qidiring.[/yellow]")
                continue
            if arg.lower() in ("save", "s", "d", "download", "export"):
                cmd = "save"
                arg = "followers"
            else:
                amt = int(arg) if arg.isdigit() else 0
                try:
                    with console.status(
                        f"[bold cyan]👥 @{current_profile.username} obunachilari (followers) yuklanmoqda...[/bold cyan]",
                        spinner="dots",
                    ):
                        followers_list = service.get_user_followers(
                            current_profile.user_id or current_profile.username,
                            amount=amt,
                        )
                    last_user_list = followers_list
                    render_user_list_to_terminal(
                        f"@{current_profile.username} — Obunachilar (Followers)",
                        followers_list,
                        total_count=current_profile.follower_count,
                    )
                except Exception as exc:
                    console.print(f"[bold red]❌ Obunachilarni olishda xatolik: {exc}[/bold red]")
                continue

        if cmd in ("following", "followings", "fol"):
            if not current_profile:
                console.print("[yellow]Avval biror username qidiring.[/yellow]")
                continue
            if arg.lower() in ("save", "s", "d", "download", "export"):
                cmd = "save"
                arg = "following"
            else:
                amt = int(arg) if arg.isdigit() else 0
                try:
                    with console.status(
                        f"[bold cyan]👥 @{current_profile.username} obunalari (following) yuklanmoqda...[/bold cyan]",
                        spinner="dots",
                    ):
                        following_list = service.get_user_following(
                            current_profile.user_id or current_profile.username,
                            amount=amt,
                        )
                    last_user_list = following_list
                    render_user_list_to_terminal(
                        f"@{current_profile.username} — Obunalar (Following)",
                        following_list,
                        total_count=current_profile.following_count,
                    )
                except Exception as exc:
                    console.print(f"[bold red]❌ Obunalarni olishda xatolik: {exc}[/bold red]")
                continue

        if cmd in ("st", "story", "stories"):
            if not current_profile:
                console.print("[yellow]Avval biror username qidiring.[/yellow]")
                continue
            if not current_profile.stories:
                console.print(f"[yellow]@{current_profile.username} profilida hozir faol 24-soatlik Story yo'q.[/yellow]")
                continue
            temp_hl = HighlightItem(
                id="active_24h",
                title=f"@{current_profile.username} — Faol 24s Storylar",
                owner_username=current_profile.username,
                items=current_profile.stories,
            )
            if arg.lower() in ("save", "all", "save all", "s", "d"):
                render_highlight_stories_to_terminal(temp_hl)
                with console.status(
                    f"[bold green]⬇️ @{current_profile.username} faol storylari yuklab olinmoqda...[/bold green]",
                    spinner="dots",
                ):
                    saved_paths = service.download_all_stories(
                        current_profile.stories,
                        username=current_profile.username,
                    )
                console.print(
                    f"[bold bright_green]✅ Jami {len(saved_paths)} ta faol story yuklab olindi![/bold bright_green]"
                )
                for sp in saved_paths:
                    console.print(f"   📁 [underline cyan]{sp}[/underline cyan]")
            else:
                open_highlight_interactive(service, temp_hl)
            continue

        if cmd in ("hl", "highlight", "highlights"):
            if not current_profile:
                console.print("[yellow]Avval biror username qidiring.[/yellow]")
                continue
            if not current_profile.highlights:
                console.print(f"[yellow]@{current_profile.username} profilida Story Highlights yo'q.[/yellow]")
                continue

            sub_parts = arg.split()
            is_direct_save = False
            hl_selector = arg.strip()
            if len(sub_parts) >= 2 and sub_parts[0].lower() in ("save", "s", "d", "download"):
                is_direct_save = True
                hl_selector = sub_parts[1].strip()
            elif hl_selector.lower() in ("all", "saveall", "save"):
                is_direct_save = True
                hl_selector = "all"
            elif not hl_selector:
                hl_selector = "1"

            if hl_selector.lower() == "all":
                all_saved = []
                with console.status(
                    f"[bold green]⬇️ @{current_profile.username} ning barcha {len(current_profile.highlights)} ta Highlightlari yuklab olinmoqda...[/bold green]",
                    spinner="dots",
                ):
                    for hl_meta in current_profile.highlights:
                        try:
                            hl_det = service.fetch_highlight_stories(
                                hl_meta.id,
                                fallback_highlight=hl_meta,
                            )
                            all_saved.extend(
                                service.download_all_highlight_stories(
                                    hl_det,
                                    include_cover=True,
                                )
                            )
                        except Exception:
                            continue
                console.print(
                    f"[bold bright_green]✅ Jami {len(all_saved)} ta Highlight story fayli yuklab olindi![/bold bright_green]"
                )
                for sp in all_saved:
                    console.print(f"   📁 [underline cyan]{sp}[/underline cyan]")
                continue

            target_hl_id = ""
            selected_hl_obj: Optional[HighlightItem] = None
            if hl_selector.isdigit() and int(hl_selector) <= len(current_profile.highlights):
                idx_hl = int(hl_selector)
                if idx_hl >= 1:
                    selected_hl_obj = current_profile.highlights[idx_hl - 1]
                    target_hl_id = selected_hl_obj.id
            else:
                target_hl_id = hl_selector
                selected_hl_obj = next(
                    (h for h in current_profile.highlights if h.id == target_hl_id),
                    None,
                )

            if not target_hl_id:
                console.print(
                    f"[red]❌ Highlight topilmadi (1..{len(current_profile.highlights)} oralig'ida kiriting).[/red]"
                )
                continue

            try:
                with console.status(
                    f"[bold yellow]✨ Highlight ({target_hl_id}) storylari yuklanmoqda...[/bold yellow]",
                    spinner="dots",
                ):
                    hl_detail = service.fetch_highlight_stories(
                        target_hl_id,
                        fallback_highlight=selected_hl_obj,
                    )
                if is_direct_save:
                    render_highlight_stories_to_terminal(hl_detail)
                    with console.status(
                        f"[bold green]⬇️ '{hl_detail.title}' ichidagi barcha {len(hl_detail.items)} ta story yuklab olinmoqda...[/bold green]",
                        spinner="dots",
                    ):
                        saved_paths = service.download_all_highlight_stories(
                            hl_detail,
                            include_cover=True,
                        )
                    console.print(
                        f"[bold bright_green]✅ Jami {len(saved_paths)} ta story yuklab olindi![/bold bright_green]"
                    )
                    for sp in saved_paths:
                        console.print(f"   📁 [underline cyan]{sp}[/underline cyan]")
                else:
                    open_highlight_interactive(service, hl_detail)
            except Exception as exc:
                console.print(f"[bold red]❌ Highlight yuklashda xatolik: {exc}[/bold red]")
            continue

        if cmd in ("images", "img", "posts", "p") and not arg:
            if current_profile:
                render_posts_images_to_terminal(current_profile)
            else:
                console.print("[yellow]Avval biror username qidiring.[/yellow]")
            continue

        if cmd in ("post", "p") and arg.isdigit():
            if current_profile:
                render_single_post_detail(current_profile, int(arg))
            else:
                console.print("[yellow]Avval biror username qidiring.[/yellow]")
            continue

        if cmd == "json":
            if current_profile:
                json_str = json.dumps(current_profile.raw_data, indent=2, ensure_ascii=False)
                console.print(Syntax(json_str, "json", theme="monokai", word_wrap=True))
            else:
                console.print("[yellow]Avval biror username qidiring.[/yellow]")
            continue

        if cmd == "save" and not arg:
            if current_profile:
                render_download_center_panel(current_profile)
            else:
                console.print("[yellow]Avval biror username qidiring.[/yellow]")
            continue

        if cmd == "save" and arg:
            if not current_profile:
                console.print("[yellow]Avval biror username qidiring.[/yellow]")
                continue

            sub = arg.lower().strip()

            # 1. SAVE ALL (Full Profile Archive)
            if sub in ("all", "all media", "everything", "hammasi", "barchasi"):
                with console.status(
                    f"[bold bright_green]🚀 @{current_profile.username} profilidagi BARCHA ma'lumotlar "
                    f"(Avatar, Storylar, {len(current_profile.highlights)} ta Highlight, Post/Reels, "
                    f"Obunachilar, Obunalar va Info) yuklab olinmoqda...[/bold bright_green]",
                    spinner="dots",
                ):
                    results = service.download_everything_for_profile(
                        current_profile,
                        include_followers=True,
                    )
                render_download_everything_summary(current_profile.username, results)
                continue

            # 2. SAVE AVATAR
            if sub in ("avatar", "av", "pic", "photo"):
                saved = service.save_media_to_downloads(
                    current_profile.profile_pic_url or current_profile.local_avatar_path,
                    f"{current_profile.username}_avatar_hd",
                    username=current_profile.username,
                    category="avatar",
                )
                if saved:
                    console.print(f"[bold green]✅ Full HD Avatar saqlandi: {saved}[/bold green]")
                else:
                    console.print("[red]❌ Avatarni saqlab bo'lmadi.[/red]")
                continue

            # 3. SAVE ACTIVE 24H STORIES
            if sub in ("st", "story", "stories"):
                if not current_profile.stories:
                    console.print(f"[yellow]@{current_profile.username} profilida faol 24s story yo'q.[/yellow]")
                    continue
                with console.status(
                    f"[bold green]⬇️ @{current_profile.username} faol 24s storylari yuklab olinmoqda...[/bold green]",
                    spinner="dots",
                ):
                    saved_paths = service.download_all_stories(
                        current_profile.stories,
                        username=current_profile.username,
                    )
                console.print(f"[bold bright_green]✅ {len(saved_paths)} ta faol story saqlandi![/bold bright_green]")
                for sp in saved_paths:
                    console.print(f"   📁 [underline cyan]{sp}[/underline cyan]")
                continue

            # 4. SAVE ALL HIGHLIGHTS
            if sub in ("hl", "highlight", "highlights"):
                if not current_profile.highlights:
                    console.print(f"[yellow]@{current_profile.username} profilida Highlightlar yo'q.[/yellow]")
                    continue
                all_saved: list[Path] = []
                with console.status(
                    f"[bold green]⬇️ @{current_profile.username} ning barcha {len(current_profile.highlights)} ta Highlightlari yuklab olinmoqda...[/bold green]",
                    spinner="dots",
                ):
                    for hl_meta in current_profile.highlights:
                        try:
                            hl_det = service.fetch_highlight_stories(hl_meta.id, fallback_highlight=hl_meta)
                            all_saved.extend(service.download_all_highlight_stories(hl_det, include_cover=True))
                        except Exception:
                            continue
                console.print(
                    f"[bold bright_green]✅ Jami {len(all_saved)} ta Highlight fayli saqlandi![/bold bright_green]"
                )
                for sp in all_saved:
                    console.print(f"   📁 [underline cyan]{sp}[/underline cyan]")
                continue

            # 5. SAVE ALL POSTS OR REELS
            if sub in ("posts", "post", "reels", "reel", "clips"):
                only_reels = sub in ("reels", "reel", "clips")
                with console.status(
                    f"[bold green]⬇️ @{current_profile.username} {'Reels videolari' if only_reels else 'barcha postlari'} yuklab olinmoqda...[/bold green]",
                    spinner="dots",
                ):
                    all_posts = current_profile.posts
                    if current_profile.media_count > len(all_posts) and not current_profile.is_private:
                        fetched = service.fetch_all_user_posts(
                            current_profile.user_id or current_profile.username,
                            max_amount=0,
                        )
                        if fetched:
                            all_posts = fetched
                            current_profile.posts = fetched
                    saved_posts: list[Path] = []
                    for p in all_posts:
                        if only_reels and p.product_type != "clips" and p.media_type != "video":
                            continue
                        saved_posts.extend(service.download_all_post_media(p))
                console.print(
                    f"[bold bright_green]✅ Jami {len(saved_posts)} ta post/reel fayli saqlandi![/bold bright_green]"
                )
                for sp in saved_posts:
                    console.print(f"   📁 [underline cyan]{sp}[/underline cyan]")
                continue

            # 6. SAVE FOLLOWERS LIST (.txt + .json)
            if sub in ("followers", "follower", "f"):
                with console.status(
                    f"[bold cyan]👥 @{current_profile.username} obunachilar ro'yxati yuklab olinmoqda va faylga saqlanmoqda...[/bold cyan]",
                    spinner="dots",
                ):
                    f_list = service.get_user_followers(
                        current_profile.user_id or current_profile.username,
                        amount=0,
                    )
                    saved_files = service.export_user_list(
                        current_profile.username,
                        "followers",
                        f_list,
                    )
                console.print(
                    f"[bold bright_green]✅ {len(f_list)} ta obunachi ro'yxati saqlandi![/bold bright_green]"
                )
                for sf in saved_files:
                    console.print(f"   📁 [underline cyan]{sf}[/underline cyan]")
                continue

            # 7. SAVE FOLLOWING LIST (.txt + .json)
            if sub in ("following", "followings", "fol"):
                with console.status(
                    f"[bold cyan]👥 @{current_profile.username} obunalar ro'yxati yuklab olinmoqda va faylga saqlanmoqda...[/bold cyan]",
                    spinner="dots",
                ):
                    fol_list = service.get_user_following(
                        current_profile.user_id or current_profile.username,
                        amount=0,
                    )
                    saved_files = service.export_user_list(
                        current_profile.username,
                        "following",
                        fol_list,
                    )
                console.print(
                    f"[bold bright_green]✅ {len(fol_list)} ta obuna ro'yxati saqlandi![/bold bright_green]"
                )
                for sf in saved_files:
                    console.print(f"   📁 [underline cyan]{sf}[/underline cyan]")
                continue

            # 8. SAVE PROFILE INFO (.txt + .json)
            if sub in ("info", "profile", "bio", "json"):
                saved_files = service.export_profile_info(current_profile)
                console.print("[bold bright_green]✅ Profil ma'lumotlari (.txt va .json) saqlandi![/bold bright_green]")
                for sf in saved_files:
                    console.print(f"   📁 [underline cyan]{sf}[/underline cyan]")
                continue

            # 9. SAVE SPECIFIC POST BY NUMBER
            if arg.isdigit():
                idx = int(arg)
                if 1 <= idx <= len(current_profile.posts):
                    p = current_profile.posts[idx - 1]
                    with console.status(
                        f"[bold green]⬇️ Post #{idx} ({p.code}) yuklab olinmoqda...[/bold green]",
                        spinner="dots",
                    ):
                        saved_files = service.download_all_post_media(p)
                    if saved_files:
                        for sf in saved_files:
                            console.print(f"[bold green]✅ Post #{idx} saqlandi: {sf}[/bold green]")
                    else:
                        console.print("[red]❌ Post mediasini saqlab bo'lmadi.[/red]")
                else:
                    console.print(f"[red]❌ Post #{idx} topilmadi.[/red]")
                continue

            # 10. Otherwise try downloading arg as a shortcode or URL
            try:
                with console.status(
                    f"[bold green]⬇️ '{arg}' yuklab olinmoqda...[/bold green]",
                    spinner="dots",
                ):
                    saved_list = service.download_by_url_or_shortcode(arg)
                console.print(
                    f"[bold bright_green]✅ Jami {len(saved_list)} ta fayl saqlandi![/bold bright_green]"
                )
                for sp in saved_list:
                    console.print(f"   📁 [underline cyan]{sp}[/underline cyan]")
            except Exception as exc:
                console.print(f"[red]❌ Yuklab olishda xatolik: {exc}[/red]")
            continue

        if cmd == "open" and arg:
            if not current_profile:
                console.print("[yellow]Avval biror username qidiring.[/yellow]")
                continue
            if arg.lower() == "avatar":
                if current_profile.local_avatar_path and current_profile.local_avatar_path.exists():
                    service.open_in_system_viewer(current_profile.local_avatar_path)
                    console.print(f"[green]🖼️ Avatar ochildi: {current_profile.local_avatar_path}[/green]")
                else:
                    console.print("[red]❌ Avatar fayli topilmadi.[/red]")
            elif arg.isdigit():
                idx = int(arg)
                if 1 <= idx <= len(current_profile.posts):
                    p = current_profile.posts[idx - 1]
                    with console.status(
                        f"[bold cyan]⬇️ Post #{idx} ({p.code}) tayyorlanmoqda...[/bold cyan]",
                        spinner="dots",
                    ):
                        saved = service.download_post_media(p)
                    if saved and saved.exists():
                        service.open_in_system_viewer(saved)
                        console.print(f"[green]▶️ Post #{idx} ochildi va saqlandi: {saved}[/green]")
                    else:
                        console.print("[red]❌ Post mediasini ochib bo'lmadi.[/red]")
                else:
                    console.print(f"[red]❌ Post #{idx} topilmadi.[/red]")
            continue

        # Otherwise treat input as an Instagram username or search command
        target_username = arg if cmd in ("search", "s", "user", "u") and arg else raw_cmd
        clean_target = service.normalize_username(target_username)
        if not clean_target:
            continue

        try:
            with console.status(
                f"[bold cyan]🔍 Instagramdan @{clean_target} real ma'lumotlari yuklanmoqda...[/bold cyan]",
                spinner="dots",
            ):
                current_profile = service.fetch_real_profile(clean_target)
            render_profile_to_terminal(current_profile, show_post_images=show_images)
        except Exception as exc:
            console.print(f"[bold red]❌ Xatolik: {exc}[/bold red]")


def run_cli() -> None:
    """CLI entry point for `instaterminal` command."""
    parser = argparse.ArgumentParser(
        prog="instaterminal",
        description="InstaTerminal — 100% Real Instagram Terminal CLI & Full Downloader",
    )
    parser.add_argument(
        "username",
        nargs="?",
        default=None,
        help="Qidirilayotgan Instagram @username yoki URL (ixtiyoriy)",
    )
    parser.add_argument(
        "-i",
        "--images",
        action="store_true",
        help="Postlarning rasmlarini ham terminalda darhol chizib ko'rsatish",
    )
    parser.add_argument(
        "-d",
        "--download-all",
        action="store_true",
        help="Profilning BARCHA ma'lumotlarini (Avatar, Story, Highlight, Post/Reel, Followers, Info) darhol yuklab olish",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Ma'lumotni chiqargandan so'ng interaktiv rejimga kirmasdan tugatish",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Profil ma'lumotlarini JSON formatida chiqarish",
    )
    parser.add_argument(
        "--followers",
        action="store_true",
        help="Profilning obunachilar (followers) ro'yxatini ko'rish",
    )
    parser.add_argument(
        "--following",
        action="store_true",
        help="Profilning obunalar (following) ro'yxatini ko'rish",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=0,
        help="Obunachi yoki obunalar soni (0 = barchasi)",
    )
    parser.add_argument(
        "--login",
        action="store_true",
        help="Yangi Instagram akkauntga kirish va sessiyani xotirada saqlash",
    )
    parser.add_argument(
        "--logout",
        action="store_true",
        help="Saqlangan Instagram sessiyasini o'chirish",
    )
    parser.add_argument(
        "-u",
        "--update",
        action="store_true",
        help="GitHub'dan eng oxirgi yangilanishni tortib olish (git pull)",
    )
    parser.add_argument(
        "-v",
        "--version",
        action="version",
        version=f"InstaTerminal v{__version__}",
    )
    args = parser.parse_args()

    if args.update:
        run_self_update()
        return

    service = InstaClientService()
    if args.logout:
        service.logout()
        console.print("[bold yellow]🔓 Saqlangan Instagram sessiyasi o'chirildi.[/bold yellow]")
        return

    service.ensure_default_session()
    if args.login:
        prompt_terminal_login(service)
        if not args.username and not args.download_all and not args.once:
            return

    if (args.download_all or args.followers or args.following or args.json or args.once) and not service.authenticated:
        prompt_terminal_login(service)

    if args.download_all:
        target = args.username or service.username
        with console.status(
            f"[bold cyan]🔍 @{service.normalize_username(target)} profili yuklanmoqda...[/bold cyan]",
            spinner="dots",
        ):
            profile = service.fetch_real_profile(target)
        render_profile_to_terminal(profile, show_post_images=args.images)
        with console.status(
            f"[bold bright_green]🚀 @{profile.username} ning BARCHA ma'lumotlari yuklab olinmoqda...[/bold bright_green]",
            spinner="dots",
        ):
            results = service.download_everything_for_profile(profile, include_followers=True)
        render_download_everything_summary(profile.username, results)
        return

    if args.followers:
        target = args.username or service.username
        profile = service.fetch_real_profile(target, download_media=False)
        followers_list = service.get_user_followers(profile.user_id or target, amount=args.count)
        render_user_list_to_terminal(
            f"@{profile.username} — Obunachilar (Followers)",
            followers_list,
            total_count=profile.follower_count,
        )
        return

    if args.following:
        target = args.username or service.username
        profile = service.fetch_real_profile(target, download_media=False)
        following_list = service.get_user_following(profile.user_id or target, amount=args.count)
        render_user_list_to_terminal(
            f"@{profile.username} — Obunalar (Following)",
            following_list,
            total_count=profile.following_count,
        )
        return

    if args.json:
        target = args.username or service.username
        profile = service.fetch_real_profile(target, download_media=False)
        console.print_json(data=profile.raw_data)
        return

    if args.once:
        target = args.username or service.username
        profile = service.fetch_real_profile(target)
        render_profile_to_terminal(profile, show_post_images=args.images)
        return

    run_interactive_loop(
        service=service,
        initial_username=args.username,
        show_images=args.images,
    )


if __name__ == "__main__":
    run_cli()
