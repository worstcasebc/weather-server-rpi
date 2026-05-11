from PIL import Image
from pack import quantize_and_pack, PALETTE_INDICES


def test_pack_size_is_192000():
    img = Image.new("RGB", (800, 480), (255, 255, 255))
    raw = quantize_and_pack(img)
    assert len(raw) == 192_000


def test_white_image_is_all_0x11():
    img = Image.new("RGB", (800, 480), (255, 255, 255))
    raw = quantize_and_pack(img)
    assert raw[:4] == bytes([0x11, 0x11, 0x11, 0x11])


def test_black_image_is_all_0x00():
    img = Image.new("RGB", (800, 480), (0, 0, 0))
    raw = quantize_and_pack(img)
    assert raw[:4] == bytes([0x00, 0x00, 0x00, 0x00])


def test_high_nibble_is_left_pixel():
    img = Image.new("RGB", (800, 480), (255, 255, 255))
    img.putpixel((0, 0), (0, 0, 0))
    raw = quantize_and_pack(img)
    assert raw[0] == 0x01


def test_palette_indices_match_hardware():
    assert PALETTE_INDICES["BLACK"]  == 0x0
    assert PALETTE_INDICES["WHITE"]  == 0x1
    assert PALETTE_INDICES["YELLOW"] == 0x2
    assert PALETTE_INDICES["RED"]    == 0x3
    assert PALETTE_INDICES["BLUE"]   == 0x5
    assert PALETTE_INDICES["GREEN"]  == 0x6
