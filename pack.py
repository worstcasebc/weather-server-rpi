from PIL import Image

PALETTE_INDICES = {
    "BLACK":  0x0,
    "WHITE":  0x1,
    "YELLOW": 0x2,
    "RED":    0x3,
    "BLUE":   0x5,
    "GREEN":  0x6,
}

PALETTE_RGB = [
    (0,   0,   0),    # 0: Schwarz
    (255, 255, 255),  # 1: Weiß
    (255, 243,   0),  # 2: Gelb
    (220,  20,  20),  # 3: Rot
    ( 30,  60, 200),  # 4: PIL-Slot 4 -> HW-Nibble 0x5 (Blau)
    ( 20, 160,  60),  # 5: PIL-Slot 5 -> HW-Nibble 0x6 (Grün)
]
PIL_TO_HW = [0x0, 0x1, 0x2, 0x3, 0x5, 0x6]


def _palette_image() -> Image.Image:
    pal = Image.new("P", (1, 1))
    flat = []
    for r, g, b in PALETTE_RGB:
        flat += [r, g, b]
    flat += [0, 0, 0] * (256 - len(PALETTE_RGB))
    pal.putpalette(flat)
    return pal


def quantize_and_pack(img: Image.Image) -> bytes:
    if img.size != (800, 480):
        raise ValueError(f"expected 800x480, got {img.size}")
    rgb = img.convert("RGB")
    quant = rgb.quantize(palette=_palette_image(), dither=Image.Dither.FLOYDSTEINBERG)
    px = quant.load()
    out = bytearray(192_000)
    i = 0
    for y in range(480):
        for x in range(0, 800, 2):
            hi = PIL_TO_HW[px[x,     y]]
            lo = PIL_TO_HW[px[x + 1, y]]
            out[i] = ((hi & 0x0F) << 4) | (lo & 0x0F)
            i += 1
    return bytes(out)
