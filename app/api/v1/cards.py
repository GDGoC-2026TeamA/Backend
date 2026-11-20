from fastapi import APIRouter, Depends

from app.api.dependencies import user
from app.database import db
from app.schemas.cards import NewCard
from app.services import cards as cards_service

router = APIRouter()


@router.post("/tasks/{tid}/cards", status_code=201)
def card(tid: int, data: NewCard, uid=Depends(user), conn=Depends(db)):
    return cards_service.card(tid, data, uid, conn)


@router.get("/cards")
def my_cards(uid=Depends(user), conn=Depends(db)):
    return cards_service.my_cards(uid, conn)
