import shutil
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.upload import router as upload_router
from app.api.files import router as files_router
from app.api.datasets import router as datasets_router
from app.api.download import router as download_router
from app.api.search import router as search_router
from app.api.versions import router as versions_router
from app.api.stats import router as stats_router
from app.api.delete import router as delete_router
from app.api.users import router as users_router
from app.api.analytics import router as analytics_router
from app.api.sql import router as sql_router
from app.api.image import router as image_router
from app.api.activity import router as activity_router
from app.api.projects import router as projects_router

app = FastAPI(

    title="ANNAM Storage Platform",
    version="1.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "https://annam-frontend.vercel.app",  # replace with your actual Vercel URL
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def seed_storage():
    """Copy seed_data/ into storage/ on first boot (only if target dirs are empty)."""
    base = Path(__file__).resolve().parent.parent  # backend/
    seed = base / "seed_data"
    if not seed.exists():
        return

    for src_dir, dst_dir in [
        (seed / "uploads", base / "storage" / "uploads"),
        (seed / "metadata", base / "storage" / "metadata"),
    ]:
        if not src_dir.exists():
            continue
        dst_dir.mkdir(parents=True, exist_ok=True)
        if not any(dst_dir.iterdir()):  # only seed when empty
            for item in src_dir.iterdir():
                shutil.copy2(item, dst_dir / item.name)

app.include_router(datasets_router)
app.include_router(download_router)
app.include_router(upload_router)
app.include_router(files_router)
app.include_router(search_router)
app.include_router(versions_router)
app.include_router(stats_router)
app.include_router(delete_router)
app.include_router(users_router)
app.include_router(analytics_router)
app.include_router(sql_router)
app.include_router(image_router)
app.include_router(activity_router)
app.include_router(projects_router, prefix="")

@app.get("/")
def home():
    return {
        "message": "ANNAM Storage Platform Running"
    }