import io

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image

from receipts.photos import THUMBNAIL_SIZE, PhotoError, process_photo, validate_photo


def _image_file(name="receipt.jpg", fmt="JPEG", size=(200, 150), exif_make=None):
    image = Image.new("RGB", size, color="red")
    buffer = io.BytesIO()
    save_kwargs = {}
    if exif_make is not None:
        exif = Image.Exif()
        exif[271] = exif_make  # тег Make
        save_kwargs["exif"] = exif.tobytes()
    image.save(buffer, format=fmt, **save_kwargs)
    buffer.seek(0)
    content_type = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}.get(
        fmt, "application/octet-stream"
    )
    return SimpleUploadedFile(name, buffer.getvalue(), content_type=content_type)


class TestValidatePhoto:
    def test_accepts_jpeg(self):
        validate_photo(_image_file(), max_mb=5)

    def test_accepts_png(self):
        validate_photo(_image_file(name="r.png", fmt="PNG"), max_mb=5)

    def test_accepts_webp(self):
        validate_photo(_image_file(name="r.webp", fmt="WEBP"), max_mb=5)

    def test_rejects_oversized_file(self):
        file = _image_file()
        with pytest.raises(PhotoError, match="МБ"):
            validate_photo(file, max_mb=0)

    def test_rejects_non_image_content(self):
        file = SimpleUploadedFile("fake.jpg", b"not an image", content_type="image/jpeg")
        with pytest.raises(PhotoError):
            validate_photo(file, max_mb=5)

    def test_rejects_unsupported_format(self):
        file = _image_file(name="r.bmp", fmt="BMP")
        with pytest.raises(PhotoError, match="JPEG, PNG, WEBP"):
            validate_photo(file, max_mb=5)


class TestProcessPhoto:
    def test_strips_exif(self):
        file = _image_file(exif_make="TestCameraMake")
        file.seek(0)
        original = Image.open(file)
        assert original.getexif().get(271) == "TestCameraMake"

        file.seek(0)
        cleaned, _thumb = process_photo(file)
        result_image = Image.open(io.BytesIO(cleaned.read()))
        assert not dict(result_image.getexif())

    def test_preserves_original_dimensions(self):
        file = _image_file(size=(200, 150))
        cleaned, _thumb = process_photo(file)
        result_image = Image.open(io.BytesIO(cleaned.read()))
        assert result_image.size == (200, 150)

    def test_thumbnail_fits_within_bounds(self):
        file = _image_file(size=(800, 600))
        _cleaned, thumb = process_photo(file)
        thumb_image = Image.open(io.BytesIO(thumb.read()))
        assert thumb_image.width <= THUMBNAIL_SIZE[0]
        assert thumb_image.height <= THUMBNAIL_SIZE[1]

    def test_keeps_original_format(self):
        file = _image_file(name="r.png", fmt="PNG")
        cleaned, thumb = process_photo(file)
        assert Image.open(io.BytesIO(cleaned.read())).format == "PNG"
        assert Image.open(io.BytesIO(thumb.read())).format == "PNG"
