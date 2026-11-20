from typing import BinaryIO, Literal

from app.dao import materials as materials_dao
from app.services.access import required, task_for, version
from app.services.errors import ServiceError
from app.storage import bucket


def upload(
    tid: int,
    kind: Literal["previous_form", "manual", "screenshot"],
    uid,
    conn,
    *,
    stream: BinaryIO,
    filename: str | None,
    content_type: str | None,
    size: int | None,
):
    task_for(conn, tid, uid, edit=True)
    if content_type not in ("application/pdf", "image/jpeg", "image/png"):
        raise ServiceError(415, "PDF, JPG, PNG 파일을 등록하세요.")
    if size is None or size > 16 * 1024 * 1024:
        raise ServiceError(413, "파일 크기는 16MB 이하여야 합니다.")
    s3, name = bucket()
    row = materials_dao.insert_pending(conn, tid, kind, filename or "자료")
    conn.commit()
    try:
        s3.upload_fileobj(
            stream,
            name,
            f"files/v1/{row['id']}",
            ExtraArgs={"ContentType": content_type},
        )
    except Exception:
        materials_dao.mark_failed(conn, row["id"])
        conn.commit()
        raise ServiceError(503, "파일 저장에 실패했습니다.") from None
    materials_dao.mark_ready(conn, row["id"])
    return row


def list_materials(tid: int, uid, conn):
    t = task_for(conn, tid, uid)
    if t["created_by"] == uid:
        return materials_dao.list_active(conn, tid)
    v = version(conn, tid, uid)
    return materials_dao.list_shared(conn, tid, v["input_file_ids"])


def download(tid: int, fid: int, uid, conn):
    t = task_for(conn, tid, uid)
    stored = materials_dao.find_ready(conn, fid, tid)
    if not stored or (
        t["created_by"] != uid and fid not in version(conn, tid, uid)["input_file_ids"]
    ):
        raise ServiceError(404, "자료가 없습니다.")
    s3, name = bucket()
    return {
        "url": s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": name, "Key": f"files/v1/{fid}"},
            ExpiresIn=120,
        )
    }


def archive_file(tid: int, fid: int, uid, conn):
    task_for(conn, tid, uid, edit=True)
    required(materials_dao.archive(conn, fid, tid))
