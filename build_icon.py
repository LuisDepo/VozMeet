#!/usr/bin/env python3
"""
Generate VozMeet.icns from the in-app logo (blue rounded square + white microphone).
Used by both the installer .app and the installed VozMeet.app.
"""
import io
import struct
from pathlib import Path
from PIL import Image, ImageDraw

OUT = Path(__file__).parent / "app/static/icons/VozMeet.icns"
OUT.parent.mkdir(parents=True, exist_ok=True)


def draw_icon(size: int) -> Image.Image:
    """Blue rounded square background + white microphone glyph (matches favicon SVG)."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # Rounded square background
    radius = int(size * 0.225)
    d.rounded_rectangle((0, 0, size - 1, size - 1), radius=radius, fill=(0, 122, 255, 255))

    # Microphone body (rounded vertical pill, centered)
    s = size / 32  # scale factor based on 32px viewBox
    mic_x, mic_y = 12 * s, 4 * s
    mic_w, mic_h = 8 * s, 12 * s
    mic_r = 4 * s
    d.rounded_rectangle((mic_x, mic_y, mic_x + mic_w, mic_y + mic_h),
                        radius=mic_r, fill=(255, 255, 255, 255))

    # Mic stand: arc + post + base
    # Arc (curved holder below the mic)
    cx, cy = 16 * s, 14 * s
    r_outer = 6 * s
    r_inner = 4 * s
    d.pieslice([cx - r_outer, cy - r_outer, cx + r_outer, cy + r_outer],
               start=0, end=180, fill=(255, 255, 255, 255))
    # Cut out inner (creates "U" shape)
    d.pieslice([cx - r_inner, cy - r_inner, cx + r_inner, cy + r_inner],
               start=0, end=180, fill=(0, 122, 255, 255))
    # Fill area above the arc (so it doesn't look like a half-disc)
    d.rectangle([cx - r_outer, 0, cx + r_outer, cy], fill=(0, 122, 255, 255))
    # Mic body should still be there — redraw it
    d.rounded_rectangle((mic_x, mic_y, mic_x + mic_w, mic_y + mic_h),
                        radius=mic_r, fill=(255, 255, 255, 255))

    # Post (vertical line from arc to base)
    post_w = max(int(s * 0.8), 1)
    d.rectangle([cx - post_w, cy + r_inner, cx + post_w, 22 * s],
                fill=(255, 255, 255, 255))
    # Base (horizontal bar at bottom)
    base_w = 6 * s
    base_h = max(int(s * 1.2), 2)
    d.rounded_rectangle([cx - base_w / 2, 22 * s - base_h / 2,
                         cx + base_w / 2, 22 * s + base_h / 2],
                        radius=base_h / 2, fill=(255, 255, 255, 255))

    return img


def png_bytes(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def main():
    # ICNS chunk types — modern macOS uses these
    sizes = {
        b"ic07": 128,
        b"ic08": 256,
        b"ic09": 512,
        b"ic10": 1024,
        b"ic11": 32,    # 16@2x
        b"ic12": 64,    # 32@2x
        b"ic13": 256,   # 128@2x
        b"ic14": 512,   # 256@2x
    }

    chunks = []
    for type_code, size in sizes.items():
        img = draw_icon(size)
        data = png_bytes(img)
        chunk = type_code + struct.pack(">I", len(data) + 8) + data
        chunks.append(chunk)

    body = b"".join(chunks)
    header = b"icns" + struct.pack(">I", len(body) + 8)
    OUT.write_bytes(header + body)
    print(f"Wrote {OUT} ({OUT.stat().st_size:,} bytes, {len(sizes)} sizes)")


if __name__ == "__main__":
    main()
