from app.dao import cards as cards_dao
from app.schemas.cards import NewCard
from app.services.access import eligible, version
from app.services.errors import ServiceError


def card(tid: int, data: NewCard, uid, conn):
    v = version(conn, tid, uid)
    if v["id"] != data.analysisId or not any(
        s.get("itemId") == str(data.itemId) and eligible(s) for s in v["steps"]
    ):
        raise ServiceError(409, "현재 확인된 단계에서 카드를 만드세요.")
    return cards_dao.insert_card(conn, uid, v["id"], data.itemId, data.title)


def my_cards(uid, conn):
    return cards_dao.list_for_user(conn, uid)
