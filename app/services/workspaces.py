from app.dao import tasks as tasks_dao, workspaces as workspaces_dao
from app.schemas.common import Name
from app.schemas.workspaces import Invite
from app.services.access import member, required
from app.services.errors import ServiceError


def spaces(uid, conn):
    return workspaces_dao.list_for_user(conn, uid)


def create_space(data: Name, uid, conn):
    row = workspaces_dao.insert_company(conn, data.name, uid)
    workspaces_dao.insert_owner(conn, row["id"], uid)
    return row


def join(data: Invite, uid, conn):
    row = required(workspaces_dao.find_by_invite(conn, data.code))
    workspaces_dao.add_member(conn, row["id"], uid)
    return row


def invite(space: int, uid, conn):
    w = member(conn, space, uid)
    if w["kind"] != "company" or w["created_by"] != uid:
        raise ServiceError(403, "회사 공간 생성자만 초대 코드를 볼 수 있습니다.")
    return {"code": w["invite_code"]}


def leave(space: int, uid, conn):
    required(workspaces_dao.lock_membership(conn, space, uid))
    w = member(conn, space, uid)
    if w["created_by"] == uid:
        raise ServiceError(409, "공간 생성자는 나갈 수 없습니다.")
    if tasks_dao.has_shared_tasks(conn, space, uid):
        raise ServiceError(409, "등록한 업무의 공유를 먼저 해제하세요.")
    workspaces_dao.remove_member(conn, space, uid)
