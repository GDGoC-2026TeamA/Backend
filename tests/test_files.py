"""Gemini로 보내는 파일 크기 한도를 S3·DB 없이 확인한다."""

import io
from unittest.mock import MagicMock

import pytest

from app.services import files
from app.services.errors import ServiceError

MB = 1024 * 1024


class FakeS3:
    def __init__(self, sizes: dict[int, int], *, with_length=True):
        self.sizes = sizes
        self.with_length = with_length
        self.read_keys: list[str] = []

    def get_object(self, Bucket, Key):
        fid = int(Key.rsplit("/", 1)[1])
        body = MagicMock(wraps=io.BytesIO(b"x" * self.sizes[fid]))
        body.__enter__.return_value = body
        body.read.side_effect = lambda: self._read(Key, fid)
        obj = {"Body": body, "ContentType": "application/pdf"}
        if self.with_length:
            obj["ContentLength"] = self.sizes[fid]
        return obj

    def _read(self, key, fid):
        self.read_keys.append(key)
        return b"x" * self.sizes[fid]


@pytest.fixture
def limit(monkeypatch):
    monkeypatch.setattr(files, "MAX_SIZE", 3 * MB)
    monkeypatch.setattr(files, "MAX_INLINE_TOTAL", 3 * MB)


def use(monkeypatch, s3):
    monkeypatch.setattr(files, "bucket", lambda: (s3, "b"))
    return s3


def test_default_limit_fits_gemini_request():
    # base64(4/3배)로 바뀐 뒤에도 Gemini 요청 한도(약 20MB)보다 작아야 한다.
    assert files.MAX_INLINE_TOTAL * 4 / 3 < 20 * MB
    assert files.MAX_SIZE <= files.MAX_INLINE_TOTAL


def test_files_within_limit_are_attached(monkeypatch, limit):
    use(monkeypatch, FakeS3({1: 1 * MB, 2: 2 * MB}))

    with files.inline_files([{"id": 1}, {"id": 2}]) as docs:
        assert [d.path.stat().st_size for d in docs] == [1 * MB, 2 * MB]


def test_total_over_limit_is_rejected_before_download(monkeypatch, limit):
    s3 = use(monkeypatch, FakeS3({1: 2 * MB, 2: 2 * MB}))

    with pytest.raises(ServiceError) as e:
        with files.inline_files([{"id": 1}, {"id": 2}]):
            pytest.fail("한도를 넘으면 Gemini 호출 전에 막아야 한다")

    assert e.value.status_code == 413
    assert "3MB" in e.value.detail
    assert s3.read_keys == ["files/v1/1"]  # 두 번째 파일은 내려받지 않는다


def test_total_over_limit_without_content_length(monkeypatch, limit):
    use(monkeypatch, FakeS3({1: 2 * MB, 2: 2 * MB}, with_length=False))

    with pytest.raises(ServiceError) as e:
        with files.inline_files([{"id": 1}, {"id": 2}]):
            pass

    assert e.value.status_code == 413


def test_upload_rejects_file_over_limit(limit):
    insert = MagicMock()

    with pytest.raises(ServiceError) as e:
        files.upload(
            MagicMock(),
            insert,
            stream=io.BytesIO(),
            content_type="application/pdf",
            size=3 * MB + 1,
        )

    assert e.value.status_code == 413
    insert.assert_not_called()  # DB에 행을 만들지 않는다


def test_upload_accepts_file_at_limit(monkeypatch, limit):
    s3 = MagicMock()
    use(monkeypatch, s3)
    monkeypatch.setattr(files.materials_dao, "mark_ready", MagicMock())

    row = files.upload(
        MagicMock(),
        lambda: {"id": 7},
        stream=io.BytesIO(b"x"),
        content_type="application/pdf",
        size=3 * MB,
    )

    assert row == {"id": 7}
    assert s3.upload_fileobj.call_args.args[2] == "files/v1/7"
