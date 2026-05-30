from fastapi import FastAPI

from web.routers import config, credentials, health

app = FastAPI(title="ai-agent Web API", version="0.1.0")
app.include_router(health.router, prefix="/api")
app.include_router(config.router, prefix="/api")
app.include_router(credentials.router, prefix="/api")
