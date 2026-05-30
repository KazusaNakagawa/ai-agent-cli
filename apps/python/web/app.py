from fastapi import FastAPI

from web.routers import auth_mode, chat, config, credentials, health, run

app = FastAPI(title="ai-agent Web API", version="0.1.0")
app.include_router(health.router, prefix="/api")
app.include_router(config.router, prefix="/api")
app.include_router(credentials.router, prefix="/api")
app.include_router(auth_mode.router, prefix="/api")
app.include_router(run.router, prefix="/api")
app.include_router(chat.router, prefix="/api")
