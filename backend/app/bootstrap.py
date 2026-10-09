from sqlalchemy import select

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.action import Action
from app.models.terminal import Terminal


def bootstrap() -> None:
    if not settings.app_seed_defaults:
        return

    with SessionLocal() as db:
        actions_by_code = {item.code: item for item in db.scalars(select(Action)).all()}
        defaults = [
            ("START_WORK", "Start work", "BSS_START_WORK", "ENTER", 10),
            ("END_WORK", "End work", "BSS_END_WORK", "EXIT", 20),
            ("BREAK", "Break", "BSS_BREAK", "EXIT", 30),
            ("MEDICAL", "Medical", "BSS_MEDICAL", "EXIT", 40),
            ("NO_WORK", "No work", "BSS_NO_WORK", "EXIT", 50),
        ]
        for code, label, supplier_event, effect, order in defaults:
            if code not in actions_by_code:
                action = Action(
                    code=code,
                    label=label,
                    supplier_device_event=supplier_event,
                    state_effect=effect,
                    reporter_id_type="BADGE",
                    oracle_attributes={},
                    display_order=order,
                )
                db.add(action)
                db.flush()
                actions_by_code[code] = action

        terminal = db.scalar(select(Terminal).where(Terminal.code == "DEMO-01"))
        if terminal is None:
            terminal = Terminal(
                code="DEMO-01",
                name="Demo terminal",
                external_device_id="DEMO-01",
                identification_mode="BOTH",
            )
            db.add(terminal)
            db.flush()
        terminal.actions = list(actions_by_code.values())
        db.commit()


if __name__ == "__main__":
    bootstrap()
