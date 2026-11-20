from fastapi import APIRouter

from app.api.v1 import (
    analyses,
    auth,
    cards,
    jobs,
    learning,
    materials,
    social,
    tasks,
    workspaces,
)

router = APIRouter(prefix="/api/v1")
router.include_router(auth.router)
router.include_router(workspaces.router)
router.include_router(tasks.router)
router.include_router(analyses.router)
router.include_router(learning.router)
router.include_router(materials.router)
router.include_router(cards.router)
router.include_router(jobs.router)
router.include_router(social.router)
