"""Terminal Image Renderer using Pillow and Rich (Unicode Half-Block & Colored ASCII modes)."""

from __future__ import annotations

import hashlib
import math
from pathlib import Path
from typing import Optional, Union

from PIL import Image, ImageDraw
from rich.color import Color
from rich.style import Style
from rich.text import Text

from instaterminal.core.config import get_cache_dir

ASCII_CHARS = "@%#*+=-:. "


class TerminalImageRenderer:
    """Renders images directly inside the terminal using Rich Text objects."""

    @staticmethod
    def render_image(
        source: Union[str, Path, Image.Image],
        width: int = 48,
        max_height: int = 24,
        mode: str = "unicode",
    ) -> Text:
        """
        Convert an image into a Rich Text renderable.

        Args:
            source: Path to an image file or a PIL Image instance.
            width: Target character width in terminal columns.
            max_height: Maximum height in terminal rows.
            mode: "unicode" (TrueColor half-block '▀') or "ascii" (colored ASCII characters).
        """
        try:
            if isinstance(source, (str, Path)):
                img = Image.open(source).convert("RGB")
            elif isinstance(source, Image.Image):
                img = source.convert("RGB")
            else:
                raise ValueError(f"Unsupported image source: {type(source)}")
        except Exception as exc:
            return Text(f"[Rasmni o'qib bo'lmadi: {exc}]", style="bold red")

        orig_w, orig_h = img.size
        if orig_w <= 0 or orig_h <= 0:
            return Text("[Bo'sh rasm]", style="dim")

        aspect = orig_h / orig_w
        target_w = max(8, width)

        if mode == "ascii":
            # Each terminal character is roughly twice as tall as it is wide
            target_h = max(4, min(max_height, int(target_w * aspect * 0.5)))
            resized = img.resize((target_w, target_h), Image.Resampling.LANCZOS)
            return TerminalImageRenderer._to_ascii(resized)
        else:
            # In half-block mode ('▀'), each terminal row displays 2 vertical pixels
            char_rows = max(4, min(max_height, int(target_w * aspect * 0.5)))
            pixel_h = char_rows * 2
            resized = img.resize((target_w, pixel_h), Image.Resampling.LANCZOS)
            return TerminalImageRenderer._to_half_block(resized)

    @staticmethod
    def _to_half_block(img: Image.Image) -> Text:
        """Render image using '▀' where foreground is top pixel and background is bottom pixel."""
        w, h = img.size
        pixels = img.load()
        text = Text()

        for y in range(0, h - 1, 2):
            for x in range(w):
                r1, g1, b1 = pixels[x, y]
                r2, g2, b2 = pixels[x, y + 1]
                style = Style(
                    color=Color.from_rgb(r1, g1, b1),
                    bgcolor=Color.from_rgb(r2, g2, b2),
                )
                text.append("▀", style=style)
            if y + 2 < h:
                text.append("\n")

        return text

    @staticmethod
    def _to_ascii(img: Image.Image) -> Text:
        """Render image using colored ASCII density characters."""
        w, h = img.size
        pixels = img.load()
        text = Text()
        scale = len(ASCII_CHARS) - 1

        for y in range(h):
            for x in range(w):
                r, g, b = pixels[x, y]
                lum = (0.299 * r + 0.587 * g + 0.114 * b) / 255.0
                # Invert luminance so brighter pixels on dark terminal use denser characters
                idx = int((1.0 - lum) * scale)
                ch = ASCII_CHARS[max(0, min(scale, idx))]
                style = Style(color=Color.from_rgb(r, g, b), bold=(lum > 0.6))
                text.append(ch, style=style)
            if y + 1 < h:
                text.append("\n")

        return text

    @staticmethod
    def generate_procedural_image(
        seed_key: str,
        theme: str = "sunset",
        size: tuple[int, int] = (160, 120),
    ) -> Path:
        """
        Generate a vibrant procedural artwork image saved in cache for Demo mode
        or fallback thumbnails.
        """
        cache_dir = get_cache_dir()
        safe_hash = hashlib.md5(f"{seed_key}:{theme}".encode("utf-8")).hexdigest()[:12]
        out_path = cache_dir / f"gen_{safe_hash}.png"
        if out_path.exists():
            return out_path

        w, h = size
        img = Image.new("RGB", (w, h))
        draw = ImageDraw.Draw(img)

        palettes = {
            "sunset": ((253, 29, 29), (252, 176, 69), (131, 58, 180)),
            "cyber": ((0, 242, 254), (79, 172, 254), (18, 16, 46)),
            "emerald": ((17, 153, 142), (56, 239, 125), (15, 32, 39)),
            "neon": ((255, 0, 132), (51, 0, 27), (0, 210, 255)),
            "desert": ((255, 126, 95), (254, 180, 123), (44, 62, 80)),
        }
        c1, c2, c3 = palettes.get(theme, palettes["sunset"])

        pixels = img.load()
        for y in range(h):
            t = y / max(1, h - 1)
            for x in range(w):
                s = x / max(1, w - 1)
                wave = 0.5 + 0.5 * math.sin(s * 6.0 + t * 4.0)
                r = int(c1[0] * (1 - t) + c2[0] * t * wave + c3[0] * (1 - wave) * 0.35)
                g = int(c1[1] * (1 - t) + c2[1] * t * wave + c3[1] * (1 - wave) * 0.35)
                b = int(c1[2] * (1 - t) + c2[2] * t * wave + c3[2] * (1 - wave) * 0.35)
                pixels[x, y] = (
                    max(0, min(255, r)),
                    max(0, min(255, g)),
                    max(0, min(255, b)),
                )

        # Draw sun / geometric focal elements
        sun_r = min(w, h) // 4
        cx, cy = int(w * 0.5), int(h * 0.42)
        draw.ellipse(
            [cx - sun_r, cy - sun_r, cx + sun_r, cy + sun_r],
            fill=(255, 240, 200),
            outline=(255, 255, 255),
            width=2,
        )

        # Mountain silhouette at the bottom
        mountain = [
            (0, h),
            (0, int(h * 0.72)),
            (int(w * 0.28), int(h * 0.52)),
            (int(w * 0.52), int(h * 0.68)),
            (int(w * 0.76), int(h * 0.48)),
            (w, int(h * 0.66)),
            (w, h),
        ]
        draw.polygon(mountain, fill=(22, 18, 38))

        img.save(out_path, "PNG")
        return out_path

