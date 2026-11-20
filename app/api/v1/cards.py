from fastapi import APIRouter, Depends

from app.api.dependencies import user
from app.database import db
from app.schemas.cards import CardDetail, CardUpdate, NewCard
from app.services import cards as cards_service

router = APIRouter()


@router.post("/tasks/{tid}/cards", status_code=201)
def card(tid: int, data: NewCard, uid=Depends(user), conn=Depends(db)):
    return cards_service.card(tid, data, uid, conn)


@router.get("/cards")
def my_cards(uid=Depends(user), conn=Depends(db)):
    return cards_service.my_cards(uid, conn)


@router.get("/cards/{card_id}", response_model=CardDetail)
def get_card(card_id: int, uid=Depends(user), conn=Depends(db)):
    return cards_service.get_card(conn, uid, card_id)


@router.patch("/cards/{card_id}", response_model=CardDetail)
def update_card(card_id: int, changes: CardUpdate, uid=Depends(user), conn=Depends(db)):
    return cards_service.update_card(conn, uid, card_id, changes)


@router.delete("/cards/{card_id}", status_code=204)
def delete_card(card_id: int, uid=Depends(user), conn=Depends(db)):
    cards_service.delete_card(conn, uid, card_id)
