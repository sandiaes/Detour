"""Make the stored rendition of a photo (ADR 022, decision 5).

One JPEG per image: longest side ``image_max_side``, progressive, the orientation applied, the
average colour kept as the placeholder shown while the photo loads. Decoding also proves the file
is an image at all; anything Pillow cannot read or that looks like a decompression bomb is refused.
"""

import io
from dataclasses import dataclass

from PIL import Image, ImageOps

# A 12-megapixel photograph is normal; 60 million pixels is not a holiday picture.
MAX_PIXELS = 60_000_000


class UndecodableImage(ValueError):
    pass


@dataclass(frozen=True)
class Processed:
    data: bytes
    width: int
    height: int
    color: str  # "#rrggbb"


def process_image(raw: bytes, *, max_side: int, quality: int) -> Processed:
    try:
        Image.MAX_IMAGE_PIXELS = MAX_PIXELS
        with Image.open(io.BytesIO(raw)) as opened:
            if opened.format not in ("JPEG", "PNG"):
                raise UndecodableImage(f"unsupported format {opened.format}")
            image = ImageOps.exif_transpose(opened).convert("RGB")
    except UndecodableImage:
        raise
    except (OSError, ValueError, Image.DecompressionBombError, SyntaxError) as exc:
        raise UndecodableImage(type(exc).__name__) from exc
    image.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
    r, g, b = image.resize((1, 1), Image.Resampling.BOX).getpixel((0, 0))  # type: ignore[misc]
    out = io.BytesIO()
    image.save(out, format="JPEG", quality=quality, optimize=True, progressive=True)
    return Processed(out.getvalue(), image.width, image.height, f"#{r:02x}{g:02x}{b:02x}")
