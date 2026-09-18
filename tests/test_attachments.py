import base64

import pytest
from agno.media import Audio, File, Image, Video
from pydantic import ValidationError

from agent_service.agents.attachments import AttachmentError, AttachmentIn, build_media
from agent_service.config import get_settings


def _b64(data: bytes = b"conteudo") -> str:
    return base64.b64encode(data).decode()


def test_buckets_by_mime_prefix():
    media = build_media(
        [
            AttachmentIn(content_base64=_b64(), mime_type="image/png"),
            AttachmentIn(content_base64=_b64(), mime_type="audio/mpeg"),
            AttachmentIn(content_base64=_b64(), mime_type="video/mp4"),
            AttachmentIn(content_base64=_b64(), mime_type="application/pdf", filename="c.pdf"),
        ]
    )
    assert [type(m) for m in media["images"]] == [Image]
    assert [type(m) for m in media["audio"]] == [Audio]
    assert [type(m) for m in media["videos"]] == [Video]
    assert [type(m) for m in media["files"]] == [File]


def test_content_round_trips_from_base64():
    media = build_media([AttachmentIn(content_base64=_b64(b"\x89PNG"), mime_type="image/png")])
    assert media["images"][0].content == b"\x89PNG"


def test_mime_type_guessed_from_filename():
    media = build_media([AttachmentIn(content_base64=_b64(), filename="foto.jpg")])
    assert len(media["images"]) == 1


def test_url_source_is_accepted():
    media = build_media([AttachmentIn(url="https://exemplo.test/foto.png", mime_type="image/png")])
    assert media["images"][0].url == "https://exemplo.test/foto.png"


def test_requires_exactly_one_source():
    with pytest.raises(ValidationError):
        AttachmentIn(mime_type="image/png")
    with pytest.raises(ValidationError):
        AttachmentIn(content_base64=_b64(), url="https://exemplo.test/x.png")


def test_invalid_base64_is_rejected():
    with pytest.raises(AttachmentError, match="base64"):
        build_media([AttachmentIn(content_base64="isso não é base64!!", mime_type="image/png")])


def test_unsupported_file_mime_type_is_rejected():
    with pytest.raises(AttachmentError, match="inválido"):
        build_media([AttachmentIn(content_base64=_b64(), mime_type="application/x-desconhecido")])


def test_oversized_attachment_is_rejected(monkeypatch):
    monkeypatch.setattr(get_settings(), "max_attachment_mb", 1)
    big = _b64(b"0" * (2 * 1024 * 1024))
    with pytest.raises(AttachmentError, match="limite"):
        build_media([AttachmentIn(content_base64=big, mime_type="image/png")])
