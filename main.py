import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from api.routes import router as dashboard_router
from api.webhook import router as webhook_router
from core.pipeline import dedupe_deletion_history
from database import SessionLocal, init_db, migrate_db
from scheduler import start_scheduler, stop_scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    migrate_db()
    db = SessionLocal()
    try:
        removed = dedupe_deletion_history(db)
        if removed:
            logging.getLogger("purgearr.main").info(f"[Historique] {removed} doublon(s) fusionné(s)")
    finally:
        db.close()
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(title="Purgearr", version="0.5.0-beta", lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")
app.include_router(webhook_router)
app.include_router(dashboard_router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=7979, reload=False)
