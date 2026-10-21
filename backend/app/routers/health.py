import hmac

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.services.operational_metrics import collect_operational_metrics

router = APIRouter(prefix="/api/v1/health", tags=["health"])


@router.get("/live")
def live():
    return {"status": "ok"}


@router.get("/ready")
def ready(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {"status": "ready"}


@router.get("/operational")
def operational(request: Request, response: Response):
    token = settings.operational_metrics_token
    supplied = request.headers.get("authorization", "")
    expected = f"Bearer {token}" if token else ""
    if not token or len(token) < 32 or not hmac.compare_digest(supplied, expected):
        raise HTTPException(status_code=401, detail="unauthorized", headers={"Cache-Control": "no-store"})
    response.headers["Cache-Control"] = "no-store"
    try:
        return collect_operational_metrics()
    except Exception:
        raise HTTPException(status_code=503, detail="operational metrics unavailable",
                            headers={"Cache-Control": "no-store"})
