from enum import StrEnum


class IdentificationMode(StrEnum):
    RFID = "RFID"
    KEYPAD = "KEYPAD"
    BOTH = "BOTH"


class IdentificationMethod(StrEnum):
    RFID = "RFID"
    KEYPAD = "KEYPAD"


class StateEffect(StrEnum):
    ENTER = "ENTER"
    EXIT = "EXIT"


class WorkerState(StrEnum):
    INSIDE = "INSIDE"
    OUTSIDE = "OUTSIDE"


class DeliveryStatus(StrEnum):
    PENDING = "PENDING"
    SENDING = "SENDING"
    RETRY = "RETRY"
    SENT = "SENT"
    REJECTED = "REJECTED"
    UNKNOWN = "UNKNOWN"
