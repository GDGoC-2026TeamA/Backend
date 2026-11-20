from pathlib import Path
from typing import BinaryIO, Literal

from app.dao import materials as materials_dao
from app.schemas.tasks import SampleRequest
from app.services import files
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
    return files.upload(
        conn,
        lambda: materials_dao.insert_pending(conn, tid, kind, filename or "자료"),
        stream=stream,
        content_type=content_type,
        size=size,
    )


SAMPLES_DIR = Path(__file__).resolve().parent.parent / "samples"

# scenario -> [(자료 종류, 파일명)]. 파일은 app/samples/{scenario}/ 아래에 둔다.
SAMPLES: dict[str, list[tuple[str, str]]] = {
    "inventory": [
        ("previous_form", "기존_입고_처리_대장.pdf"),
        ("manual", "신규_재고관리_시스템_매뉴얼.pdf"),
    ],
}


def load_samples(tid: int, data: SampleRequest, uid, conn):
    task_for(conn, tid, uid, edit=True)
    created = []
    for kind, filename in SAMPLES[data.scenario]:
        path = SAMPLES_DIR / data.scenario / filename
        with path.open("rb") as stream:
            row = files.upload(
                conn,
                lambda k=kind, n=filename: materials_dao.insert_pending(conn, tid, k, n),
                stream=stream,
                content_type="application/pdf",
                size=path.stat().st_size,
            )
        created.append(
            {"id": row["id"], "kind": kind, "filename": filename, "status": "ready"}
        )
    return {"materials": created}


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
            Params={"Bucket": name, "Key": files.object_key(fid)},
            ExpiresIn=120,
        )
    }


def archive_file(tid: int, fid: int, uid, conn):
    task_for(conn, tid, uid, edit=True)
    required(materials_dao.archive(conn, fid, tid))
