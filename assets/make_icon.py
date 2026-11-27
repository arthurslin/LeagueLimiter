"""Draws the League Limiter icon (assets/icon.ico + assets/icon.png). Needs Pillow.

Design: dark rounded tile with a gold border, a gold "games left" progress
ring with a gap, and an upright sword in the middle.
"""
import math
import os

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
S = 1024  # draw big, downsample for smooth edges

BG = (16, 20, 28, 255)
BG2 = (30, 36, 48, 255)
GOLD = (200, 170, 110, 255)
GOLD_LIGHT = (240, 214, 150, 255)
GOLD_DARK = (120, 96, 52, 255)
TEAL = (10, 200, 185, 255)


def draw():
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # Tile with border
    m = 40
    d.rounded_rectangle([m, m, S - m, S - m], radius=200, fill=GOLD_DARK)
    d.rounded_rectangle([m + 22, m + 22, S - m - 22, S - m - 22], radius=180, fill=BG)
    d.rounded_rectangle([m + 40, m + 40, S - m - 40, S - m - 40], radius=165, outline=BG2, width=14)

    # Progress ring: dim track + gold arc with a gap at the top
    c = S / 2
    r = 330
    w = 64
    box = [c - r, c - r, c + r, c + r]
    d.arc(box, 0, 360, fill=BG2, width=w)
    d.arc(box, -90 + 28, 270 - 28 - 70, fill=GOLD, width=w)
    # Teal pip marking the remaining game
    ang = math.radians(270 - 28 - 35)
    px, py = c + r * math.cos(ang) - 0, c + r * math.sin(ang)
    pr = w * 0.55
    d.ellipse([px - pr, py - pr, px + pr, py + pr], fill=TEAL)

    # Sword (points up)
    blade_w = 72
    tip_y = 270
    guard_y = 575
    d.polygon([(c, tip_y), (c + blade_w / 2, tip_y + 80), (c + blade_w / 2, guard_y),
               (c - blade_w / 2, guard_y), (c - blade_w / 2, tip_y + 80)], fill=GOLD_LIGHT)
    d.line([(c, tip_y + 40), (c, guard_y - 10)], fill=GOLD_DARK, width=10)  # fuller
    # Cross-guard
    gw, gh = 260, 50
    d.rounded_rectangle([c - gw / 2, guard_y, c + gw / 2, guard_y + gh], radius=20, fill=GOLD)
    # Grip and pommel
    d.rectangle([c - 26, guard_y + gh, c + 26, guard_y + gh + 80], fill=GOLD_DARK)
    pr = 38
    py = guard_y + gh + 80 + pr - 8
    d.ellipse([c - pr, py - pr, c + pr, py + pr], fill=GOLD)
    return img


def main():
    big = draw()
    sizes = [256, 128, 64, 48, 32, 24, 16]
    icon256 = big.resize((256, 256), Image.LANCZOS)
    icon256.save(os.path.join(HERE, "icon.png"))
    icon256.save(os.path.join(HERE, "icon.ico"), sizes=[(s, s) for s in sizes])
    print("wrote icon.png and icon.ico")


if __name__ == "__main__":
    main()
