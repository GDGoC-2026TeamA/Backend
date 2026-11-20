from fastapi import APIRouter, Depends

from app.api.dependencies import user
from app.database import db
from app.schemas.learning import Answers, Question, Selection
from app.services import learning as learning_service

router = APIRouter()


@router.get("/tasks/{tid}/learning-guide")
def guide(tid: int, uid=Depends(user), conn=Depends(db)):
    return learning_service.guide(tid, uid, conn)


@router.post("/tasks/{tid}/practices", status_code=201)
def practice(tid: int, data: Selection, uid=Depends(user), conn=Depends(db)):
    return learning_service.practice(tid, data, uid, conn)


@router.post("/practices/{pid}/answers")
def answer(pid: int, data: Answers, uid=Depends(user), conn=Depends(db)):
    return learning_service.answer(pid, data, uid, conn)


@router.get("/practices/{pid}/result")
def result(pid: int, uid=Depends(user), conn=Depends(db)):
    return learning_service.result(pid, uid, conn)


@router.post("/tasks/{tid}/questions", status_code=201)
def ask(tid: int, data: Question, uid=Depends(user), conn=Depends(db)):
    return learning_service.ask(tid, data, uid, conn)


@router.get("/me/learning-history")
def history(uid=Depends(user), conn=Depends(db)):
    return learning_service.history(uid, conn)


@router.get("/me/learning-history/{rid}")
def history_detail(rid: int, uid=Depends(user), conn=Depends(db)):
    return learning_service.history_detail(rid, uid, conn)
