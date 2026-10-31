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
            ("START_WORK", "Start work", "BSS_START_WORK", "ENTER", 10, False, None, None),
            ("END_WORK", "End work", "BSS_END_WORK", "EXIT", 20, False, None, "end-work"),
            ("BREAK", "Break", "BSS_BREAK", "EXIT", 30, False, None, "break"),
            ("FACTORY_EXIT", "Factory exit", "BSS_FACTORY_EXIT_MENU", "EXIT", 40, True, None, "factory"),
            ("PERSONAL_MATTERS", "Personal matters", "BSS_PERSONAL_MATTERS", "EXIT", 41, False, "FACTORY_EXIT", "personal"),
            ("MEDICAL", "Medical", "BSS_MEDICAL", "EXIT", 42, False, "FACTORY_EXIT", "medical"),
            ("LEGAL_MATTERS", "Legal matters", "BSS_LEGAL_MATTERS", "EXIT", 43, False, "FACTORY_EXIT", "legal"),
            ("NO_WORK", "No work", "BSS_NO_WORK", "EXIT", 50, False, None, "no-work"),
        ]
        for code, label, supplier_event, effect, order, requires_subaction, _, visual_key in defaults:
            if code not in actions_by_code:
                action = Action(
                    code=code,
                    label=label,
                    supplier_device_event=supplier_event,
                    oracle_supplier_event="HUT_TCD_SUPP1_IN_2" if effect == "ENTER" else "HUT_TCD_SUPP1_OUT_2",
                    state_effect=effect,
                    oracle_attributes={},
                    display_order=order,
                    requires_subaction=requires_subaction,
                    visual_key=visual_key,
                )
                db.add(action)
                db.flush()
                actions_by_code[code] = action

        for code, _, supplier_event, _, _, _, parent_code, _ in defaults:
            if not parent_code:
                continue
            action = actions_by_code[code]
            parent = actions_by_code[parent_code]
            if action.parent_action_id is None and action.supplier_device_event == supplier_event:
                action.parent_action = parent

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
            terminal.actions = [item for item in actions_by_code.values() if item.code in {row[0] for row in defaults}]
        db.commit()


if __name__ == "__main__":
    bootstrap()
