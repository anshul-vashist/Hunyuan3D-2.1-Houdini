"""
Lightweight tests for user-selection image preprocessing.
"""
from PIL import Image

from selection_utils import apply_image_selection, has_transparency


def test_pixel_box_crop():
    image = Image.new("RGB", (100, 80), "white")
    selected = apply_image_selection(
        image,
        {
            "box": [20, 10, 70, 60],
            "box_format": "pixel",
            "padding": 5,
        },
    )

    assert selected.size == (60, 60)
    assert selected.mode == "RGBA"


def test_normalized_1000_box_crop():
    image = Image.new("RGB", (200, 100), "white")
    selected = apply_image_selection(
        image,
        {
            "box": [250, 200, 750, 800],
            "box_format": "normalized_1000",
            "padding": 0,
        },
    )

    assert selected.size == (100, 60)


def test_transparent_outside_box():
    image = Image.new("RGB", (64, 64), "white")
    selected = apply_image_selection(
        image,
        {
            "box": [16, 16, 48, 48],
            "box_format": "pixel",
            "crop": False,
            "transparent_outside_box": True,
        },
    )

    assert selected.size == (64, 64)
    assert has_transparency(selected)
    assert selected.getpixel((0, 0))[3] == 0
    assert selected.getpixel((32, 32))[3] == 255
