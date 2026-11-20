from unittest.mock import Mock

import pytest
from pydantic import ValidationError

from app.models.rows import CardRow
from app.schemas.cards import CardUpdate
from app.services import cards
from app.services.errors import ServiceError


@pytest.fixture
def row():
    return dict(id=17, user_id=3, analysis_id=9,
                item_id="facb7ed1-67a3-46f7-8005-8bb8f771559c",
                title="검토", overrides={"memo": "초안"},
                updated_at="2026-11-21T10:00:00Z")


def assert_owner_filter(conn):
    query, params = conn.execute.call_args.args
    assert "where user_id = %s and id = %s" in " ".join(query.lower().split())
    assert params[-2:] == (3, 17)


def test_get_card_returns_owned_card(row):
    conn = Mock()
    conn.execute.return_value.fetchone.return_value = row

    assert cards.get_card(conn, 3, 17) == CardRow.model_validate(row)
    assert_owner_filter(conn)


@pytest.mark.parametrize("payload", [
    {"title": "새 제목"},
    {"overrides": {"memo": "확인"}},
    {"overrides": {}},
])
def test_update_card_passes_only_requested_values(row, payload):
    conn = Mock()
    updated = {**row, **payload}
    conn.execute.return_value.fetchone.return_value = updated

    result = cards.update_card(conn, 3, 17, CardUpdate(**payload))

    assert result == CardRow.model_validate(updated)
    assert_owner_filter(conn)
    title, overrides, *_ = conn.execute.call_args.args[1]
    assert title == payload.get("title")
    assert (overrides.obj if overrides is not None else None) == payload.get("overrides")


@pytest.mark.parametrize("payload", [
    {}, {"title": "  "}, {"title": None}, {"overrides": None}, {"user_id": 4},
])
def test_update_rejects_invalid_payload(payload):
    with pytest.raises(ValidationError):
        CardUpdate(**payload)


def test_delete_owned_card():
    conn = Mock()
    conn.execute.return_value.fetchone.return_value = {"id": 17}

    assert cards.delete_card(conn, 3, 17) is None
    assert_owner_filter(conn)
    assert conn.execute.call_args.args[0].lstrip().upper().startswith("DELETE FROM CARDS")


@pytest.mark.parametrize(("operation", "args"), [
    (cards.get_card, ()),
    (cards.update_card, (CardUpdate(title="새 제목"),)),
    (cards.delete_card, ()),
])
def test_card_outside_owner_scope_returns_404(operation, args):
    conn = Mock()
    conn.execute.return_value.fetchone.return_value = None

    with pytest.raises(ServiceError) as error:
        operation(conn, 3, 17, *args)

    assert error.value.status_code == 404
    assert_owner_filter(conn)
