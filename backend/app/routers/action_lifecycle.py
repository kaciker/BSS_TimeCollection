from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.action import Action
from app.models.perimeter import FactoryPerimeterSettings
from app.models.time_event import TimeEvent
from app.services.configuration_service import commit_configuration


router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


def _delete_blockers(db: Session, action: Action) -> list[str]:
    blockers: list[str] = []

    if db.scalar(select(TimeEvent.id).where(TimeEvent.action_id == action.id).limit(1)) is not None:
        blockers.append("it is referenced by recorded time events")

    terminal_codes = sorted(terminal.code for terminal in action.terminals)
    if terminal_codes:
        blockers.append(f"it is assigned to terminal(s): {', '.join(terminal_codes)}")

    child_codes = sorted(child.code for child in action.subactions)
    if child_codes:
        blockers.append(f"it is the parent of sub-action(s): {', '.join(child_codes)}")

    perimeter_factories = list(db.scalars(
        select(FactoryPerimeterSettings.factory_code).where(
            FactoryPerimeterSettings.auto_exit_action_code == action.code
        )
    ).all())
    if perimeter_factories:
        blockers.append(f"it is configured as automatic factory exit for: {', '.join(sorted(perimeter_factories))}")

    return blockers


@router.delete("/actions/{action_code}")
def delete_action(action_code: str, db: Session = Depends(get_db)):
    action = db.scalar(select(Action).where(Action.code == action_code).with_for_update())
    if action is None:
        raise HTTPException(404, "Action not found")

    blockers = _delete_blockers(db, action)
    if blockers:
        raise HTTPException(
            409,
            f"Action {action_code} cannot be deleted because {'; '.join(blockers)}. Deactivate it instead.",
        )

    db.delete(action)
    commit_configuration(db)
    return {"detail": f"Action {action_code} deleted"}
