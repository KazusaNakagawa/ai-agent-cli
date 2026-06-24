from fastapi import FastAPI

from web.routers import (
    archive,
    auth_mode,
    briefing,
    chat,
    config,
    credentials,
    export,
    health,
    journal,
    run,
    state,
    usage,
)

app = FastAPI(title="ai-agent Web API", version="0.1.0")
app.include_router(health.router, prefix="/api")
app.include_router(config.router, prefix="/api")
app.include_router(credentials.router, prefix="/api")
app.include_router(auth_mode.router, prefix="/api")
app.include_router(state.router, prefix="/api")
app.include_router(run.router, prefix="/api")
app.include_router(chat.router, prefix="/api")
app.include_router(usage.router, prefix="/api")
app.include_router(briefing.router, prefix="/api")
app.include_router(archive.router, prefix="/api")
app.include_router(journal.router, prefix="/api")
app.include_router(export.router, prefix="/api")
