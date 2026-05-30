from fastapi import FastAPI

from web.routers import health

app = FastAPI(title="ai-agent Web API", version="0.1.0")
app.include_router(health.router, prefix="/api")
