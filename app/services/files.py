"""업무 자료와 작업 자료가 함께 쓰는 파일 저장·첨부 처리."""

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import BinaryIO

from app.ai.gemini_client import InlineFile
from app.config import GEMINI_MAX_INLINE_BYTES
from app.dao import materials as materials_dao
from app.services.errors import ServiceError
from app.storage import bucket

ALLOWED_TYPES = ("application/pdf", "image/jpeg", "image/png")
# 업로드한 자료는 모두 Gemini에 보낼 수 있어야 하므로 같은 한도를 쓴다.
MAX_SIZE = GEMINI_MAX_INLINE_BYTES
MAX_INLINE_TOTAL = GEMINI_MAX_INLINE_BYTES


def _mb(size: int) -> str:
    return f"{size / 1024 / 1024:g}MB"


def object_key(file_id: int) -> str:
    return f"files/v1/{file_id}"


def upload(
    conn,
    insert: Callable[[], dict],
    *,
    stream: BinaryIO,
    content_type: str | None,
    size: int | None,
):
    """
    files 행을 pending으로 만들어 커밋한 뒤 원본을 올리고 ready로 바꾼다.
    insert는 pending 행을 INSERT ... RETURNING 하는 함수다.
    """
    if content_type not in ALLOWED_TYPES:
        raise ServiceError(415, "PDF, JPG, PNG 파일을 등록하세요.")
    if size is None or size > MAX_SIZE:
        raise ServiceError(413, f"파일 크기는 {_mb(MAX_SIZE)} 이하여야 합니다.")
    s3, name = bucket()
    row = insert()
    conn.commit()
    try:
        s3.upload_fileobj(
            stream,
            name,
            object_key(row["id"]),
            ExtraArgs={"ContentType": content_type},
        )
    except Exception:
        materials_dao.mark_failed(conn, row["id"])
        conn.commit()
        raise ServiceError(503, "파일 저장에 실패했습니다.") from None
    materials_dao.mark_ready(conn, row["id"])
    return row


@contextmanager
def inline_files(files: list[dict]) -> Iterator[list[InlineFile]]:
    """
    저장된 파일을 임시 폴더로 내려받아 Gemini 첨부 형식으로 넘긴다.
    고른 파일의 합계가 MAX_INLINE_TOTAL을 넘으면 Gemini를 호출하기 전에 413으로 막는다.
    """
    s3, name = bucket()
    total = 0
    with TemporaryDirectory() as folder:
        docs = []
        for f in files:
            path = Path(folder) / str(f["id"])
            obj = s3.get_object(Bucket=name, Key=object_key(f["id"]))
            with obj["Body"] as stream:
                # 크기 정보가 있으면 내려받기 전에 확인하고, 없으면 읽은 뒤 확인한다.
                size = obj.get("ContentLength")
                if size is not None and total + size > MAX_INLINE_TOTAL:
                    raise _too_large()
                data = stream.read()
            total += len(data)
            if total > MAX_INLINE_TOTAL:
                raise _too_large()
            path.write_bytes(data)
            docs.append(InlineFile(path, obj["ContentType"]))
        yield docs


def _too_large() -> ServiceError:
    return ServiceError(
        413,
        f"AI에 한 번에 보낼 수 있는 자료는 합계 {_mb(MAX_INLINE_TOTAL)}까지입니다. "
        "자료 수를 줄여 다시 시도하세요.",
    )


def source_view(sources: list[dict] | None) -> dict | None:
    """명세의 대표 근거 형식 { materialId, page }로 첫 근거를 바꾼다."""
    if not sources:
        return None
    first = sources[0]
    return {"materialId": first["fileId"], "page": first["location"]}
