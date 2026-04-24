"""
Generates a simple .ico file for the desktop shortcut.
Run this before building if you want a custom icon.
Requires: pip install Pillow
"""

from PIL import Image, ImageDraw, ImageFont
import os

def create_icon():
    sizes = [16, 32, 48, 64, 128, 256]
    images = []

    for size in sizes:
        img  = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        # Dark background circle
        draw.ellipse([2, 2, size-2, size-2], fill="#1a1a2e")

        # Pokemon ball style
        mid = size // 2
        draw.ellipse([2, 2, size-2, size-2],
                     outline="#e94560", width=max(1, size//16))

        # Horizontal line
        draw.line([2, mid, size-2, mid],
                  fill="#e94560", width=max(1, size//16))

        # Center button
        r = size // 6
        draw.ellipse([mid-r, mid-r, mid+r, mid+r], fill="#e94560")
        draw.ellipse([mid-r+2, mid-r+2, mid+r-2, mid+r-2],
                     fill="white")

        images.append(img)

    out = os.path.join(os.path.dirname(__file__), "..", "icon.ico")
    images[0].save(out, format="ICO", sizes=[(s,s) for s in sizes],
                   append_images=images[1:])
    print(f"✅ Icon saved to {out}")

if __name__ == "__main__":
    create_icon()