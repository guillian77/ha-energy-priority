
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter

S = 512
SS = 2

BOLT = [
    (0.585, 0.055), (0.290, 0.545), (0.462, 0.545),
    (0.395, 0.945), (0.715, 0.450), (0.525, 0.450),
]


def gradient(size, c1, c2):
    img = Image.new("RGB", (size, size))
    px = img.load()
    for y in range(size):
        for x in range(size):
            t = max(0.0, min(1.0, (x + y) / (2 * size)))
            px[x, y] = tuple(int(c1[i] + (c2[i] - c1[i]) * t) for i in range(3))
    return img


def rounded_mask(size, radius_ratio=0.235):
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [0, 0, size - 1, size - 1], radius=int(size * radius_ratio), fill=255
    )
    return mask


def build():
    size = S * SS
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    img.paste(gradient(size, (11, 18, 32), (28, 44, 72)).convert("RGBA"), (0, 0), rounded_mask(size))

    pts = [(size * (0.455 + (x - 0.5) * 0.80), size * (0.44 + (y - 0.5) * 0.80)) for x, y in BOLT]

    glow = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(glow).polygon(pts, fill=(255, 176, 32, 140))
    img.alpha_composite(glow.filter(ImageFilter.GaussianBlur(int(size * 0.05))))

    d = ImageDraw.Draw(img)
    d.polygon(pts, fill=(255, 176, 32, 255))

    bw, gap = size * 0.062, size * 0.036
    heights = [0.075, 0.125, 0.175]
    x0 = size * 0.90 - (3 * bw + 2 * gap)
    bottom = size * 0.845
    for i, h in enumerate(heights):
        x = x0 + i * (bw + gap)
        d.rounded_rectangle([x, bottom - size * h, x + bw, bottom], radius=bw / 2.6, fill=(56, 189, 248, 235))

    return img.resize((S, S), Image.LANCZOS)


icon = build()
brand = Path("/opt/data/workspace/ha-energy-priority/custom_components/energy_priority/brand")
brand.mkdir(parents=True, exist_ok=True)
icon.save(brand / "icon.png")
icon.resize((256, 256), Image.LANCZOS).save(brand / "icon@2x.png".replace("@2x", ""))
icon.resize((256, 256), Image.LANCZOS).save(brand / "dark_icon.png")
icon.resize((256, 256), Image.LANCZOS).save(brand / "icon_256.png")
print("ok", [p.name for p in sorted(brand.iterdir())])
