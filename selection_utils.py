"""
Image selection preprocessing for object-focused Hunyuan3D generation.
"""
import base64
from io import BytesIO
from typing import Any, Optional

from PIL import Image, ImageChops, ImageFilter


def load_image_from_base64(image: str) -> Image.Image:
    """Load a PIL image from raw base64 or a data URI."""
    if "," in image and image.lstrip().startswith("data:"):
        image = image.split(",", 1)[1]
    return Image.open(BytesIO(base64.b64decode(image)))


def image_to_base64(image: Image.Image, image_format: str = "PNG") -> str:
    """Serialize a PIL image to base64."""
    buffer = BytesIO()
    image.save(buffer, format=image_format)
    return base64.b64encode(buffer.getvalue()).decode()


def has_transparency(image: Image.Image) -> bool:
    """Return True when the image has any non-opaque alpha pixels."""
    if image.mode != "RGBA":
        return False
    alpha = image.getchannel("A")
    return alpha.getextrema()[0] < 255


def _selection_get(selection: Any, key: str, default: Any = None) -> Any:
    if selection is None:
        return default
    if isinstance(selection, dict):
        return selection.get(key, default)
    return getattr(selection, key, default)


def _box_to_pixels(box: list[float], box_format: str, size: tuple[int, int]) -> tuple[int, int, int, int]:
    width, height = size
    x1, y1, x2, y2 = [float(v) for v in box]

    if box_format == "normalized_1000":
        x1, x2 = x1 / 1000.0 * width, x2 / 1000.0 * width
        y1, y2 = y1 / 1000.0 * height, y2 / 1000.0 * height
    elif box_format == "normalized":
        x1, x2 = x1 * width, x2 * width
        y1, y2 = y1 * height, y2 * height
    elif box_format != "pixel":
        raise ValueError(f"Unsupported selection box_format: {box_format}")

    left = max(0, min(width, int(round(min(x1, x2)))))
    top = max(0, min(height, int(round(min(y1, y2)))))
    right = max(0, min(width, int(round(max(x1, x2)))))
    bottom = max(0, min(height, int(round(max(y1, y2)))))

    if right <= left or bottom <= top:
        raise ValueError(f"Invalid selection box after conversion: {[left, top, right, bottom]}")
    return left, top, right, bottom


def _expand_box(box: tuple[int, int, int, int], padding: int, size: tuple[int, int]) -> tuple[int, int, int, int]:
    width, height = size
    left, top, right, bottom = box
    return (
        max(0, left - padding),
        max(0, top - padding),
        min(width, right + padding),
        min(height, bottom + padding),
    )


def _mask_from_selection(selection: Any, size: tuple[int, int]) -> Optional[Image.Image]:
    mask_base64 = _selection_get(selection, "mask")
    if not mask_base64:
        return None

    threshold = int(_selection_get(selection, "mask_threshold", 8))
    feather = int(_selection_get(selection, "mask_feather", 1))
    invert = bool(_selection_get(selection, "invert_mask", False))

    mask_img = load_image_from_base64(mask_base64)
    if mask_img.mode == "RGBA":
        mask = mask_img.getchannel("A")
    else:
        mask = mask_img.convert("L")

    if mask.size != size:
        mask = mask.resize(size, Image.Resampling.BILINEAR)
    if invert:
        mask = ImageChops.invert(mask)
    mask = mask.point(lambda value: 255 if value >= threshold else 0)
    if feather > 0:
        mask = mask.filter(ImageFilter.GaussianBlur(radius=feather))
    return mask


def apply_image_selection(image: Image.Image, selection: Any) -> Image.Image:
    """
    Apply a user selection before image-to-3D.

    The selection can contain:
    - box: [x1, y1, x2, y2]
    - box_format: pixel, normalized, or normalized_1000
    - mask: base64 grayscale/RGBA mask
    - padding: crop padding in pixels
    - crop: crop output around selection
    """
    if selection is None:
        return image

    image = image.convert("RGBA")
    box = _selection_get(selection, "box")
    box_format = _selection_get(selection, "box_format", "normalized_1000")
    padding = int(_selection_get(selection, "padding", 24))
    crop = bool(_selection_get(selection, "crop", True))
    transparent_outside_box = bool(_selection_get(selection, "transparent_outside_box", False))

    mask = _mask_from_selection(selection, image.size)
    crop_box = None

    if box:
        crop_box = _box_to_pixels(box, box_format, image.size)
        if transparent_outside_box and mask is None:
            mask = Image.new("L", image.size, 0)
            box_mask = Image.new("L", (crop_box[2] - crop_box[0], crop_box[3] - crop_box[1]), 255)
            mask.paste(box_mask, crop_box[:2])

    if mask is not None:
        alpha = ImageChops.multiply(image.getchannel("A"), mask)
        image.putalpha(alpha)
        if crop_box is None:
            crop_box = alpha.getbbox()

    if crop and crop_box:
        image = image.crop(_expand_box(crop_box, padding, image.size))

    return image
