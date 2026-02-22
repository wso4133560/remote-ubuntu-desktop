"""FastAPI 主应用"""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .database.database import init_database, get_database
from .api.v1 import auth, setup, devices, metrics, groups
from .websocket import endpoint


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    db = init_database("sqlite+aiosqlite:///./remote_control.db")
    await db.init_db()
    yield
    await db.close()


app = FastAPI(
    title="Remote Control Server",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api/v1")
app.include_router(setup.router, prefix="/api/v1")
app.include_router(devices.router, prefix="/api/v1")
app.include_router(metrics.router, prefix="/api/v1")
app.include_router(groups.router, prefix="/api/v1")
app.include_router(endpoint.router)


@app.get("/health")
async def health_check():
    """健康检查端点"""
    return {
        "status": "healthy",
        "connections": endpoint.connection_manager.get_connection_count(),
    }


@app.get("/")
async def root():
    """根端点"""
    return {"message": "Remote Control Server API"}
