from fastapi import FastAPI

from app.routers import admin, health, terminal

app = FastAPI(
    title="BSS Time Collection",
    version="0.1.0",
    description="External Time Collection Device event collector for Oracle HCM Time and Labor.",
)

app.include_router(health.router)
app.include_router(terminal.router)
app.include_router(admin.router)


@app.get("/api/v1/meta")
def meta():
    return {
        "name": "BSS Time Collection",
        "version": "0.1.0",
        "authentication": "disabled",
        "scope": "external-time-collection-device",
    }
