"""Shared, strict normalization for 32-bit RFID reader identifiers."""
from sqlalchemy import BigInteger, Numeric, String, case, cast, func, literal

UINT32_LIMIT = 2**32


def resolve_sql_for_candidates(template: str, candidates: tuple[str, ...]) -> str:
    """Expand only the count of parameter placeholders in a fixed SQL template."""
    markers = ("IN (?, ?)", "IN ({placeholders})")
    marker = next((item for item in markers if item in template), None)
    if marker is None:
        raise ValueError("RFID lookup SQL template is missing its candidate marker")
    replacement = "IN (" + ", ".join("?" for _ in candidates) + ")"
    return template.replace(marker, replacement, 1)


def rfid_candidates(reader_id: str) -> tuple[str, ...]:
    """Return exact, numeric RAW, and byte-swapped decimal representations.

    The exact first candidate preserves the terminal's captured spelling; the
    other candidates are lookup aliases only and must never replace event data.
    """
    digits = str(reader_id)
    if not digits or not digits.isascii() or not digits.isdecimal():
        raise ValueError("RFID reader ID must contain ASCII decimal digits")
    number = int(digits)
    if number >= UINT32_LIMIT:
        raise ValueError("RFID reader ID exceeds the validated 32-bit format")
    swapped = int.from_bytes(number.to_bytes(4, "big"), "little")
    return tuple(dict.fromkeys((digits, str(number), str(swapped))))


def rfid_lookup_candidates(reader_id: str) -> tuple[str, ...]:
    """Read-only aliases covering exact, padded/unpadded RAW and byte swap."""
    exact = str(reader_id)
    base = rfid_candidates(exact)
    number = int(exact)
    swapped = int.from_bytes(number.to_bytes(4, "big"), "little")
    return tuple(dict.fromkeys((*base, f"{number:010d}", f"{swapped:010d}")))


def reader_number_to_attr_value(reader_id: str) -> str:
    """Return the byte-swapped SECURITY_DB attribute representation."""
    digits = str(reader_id)
    if not digits or not digits.isascii() or not digits.isdecimal():
        raise ValueError("RFID reader ID must contain ASCII decimal digits")
    number = int(digits)
    if number >= UINT32_LIMIT:
        raise ValueError("RFID reader ID exceeds the validated 32-bit format")
    return str(int.from_bytes(number.to_bytes(4, "big"), "little"))


def canonical_reader_id(reader_id: str) -> str:
    """Stable equivalence key for exact/padded RAW and 32-bit byte-swapped IDs.

    It is for identity comparisons only; callers retain the original ID for
    audit/history and must reject a key shared by distinct people.
    """
    digits = str(reader_id)
    rfid_candidates(digits)
    number = int(digits)
    swapped = int.from_bytes(number.to_bytes(4, "big"), "little")
    return str(min(number, swapped))


def reader_from_swapped_attribute(value: str) -> str:
    """Convert SQL's swapped attribute to the physical, zero-padded reader ID."""
    digits = str(value)
    if not digits or not digits.isascii() or not digits.isdecimal():
        raise ValueError("RFID attribute must contain ASCII decimal digits")
    number = int(digits)
    if number >= UINT32_LIMIT:
        raise ValueError("RFID attribute exceeds the validated 32-bit format")
    return f"{int.from_bytes(number.to_bytes(4, 'big'), 'little'):010d}"


def rfid_candidates_from_attribute(value: str) -> tuple[str, ...]:
    """Return reader aliases when an attribute may store RAW or swapped form."""
    digits = str(value)
    if not digits or not digits.isascii() or not digits.isdecimal():
        raise ValueError("RFID attribute must contain ASCII decimal digits")
    number = int(digits)
    if number >= UINT32_LIMIT:
        raise ValueError("RFID attribute exceeds the validated 32-bit format")
    swapped = int.from_bytes(number.to_bytes(4, "big"), "little")
    return tuple(dict.fromkeys((f"{number:010d}", str(number), f"{swapped:010d}", str(swapped))))


def rfid_equivalence_key_sql(expression, *, dialect: str):
    """SQL expression mapping equivalent uint32 RFID strings to one key."""
    text_value = func.trim(cast(expression, String))
    digits_only = text_value.op("NOT LIKE")("%[^0-9]%")
    if dialect == "sqlite":
        digits_only = text_value.op("GLOB")("[0-9]*") & ~text_value.op("GLOB")("*[^0-9]*")
    elif dialect in {"postgresql", "postgres"}:
        digits_only = text_value.op("~")("^[0-9]{1,10}$")
    valid = digits_only & (func.length(text_value) <= 10) & (func.length(text_value) > 0)
    numeric = case((valid, cast(text_value, BigInteger)), else_=None)
    valid = valid & (numeric >= 0) & (numeric < UINT32_LIMIT)
    byte1 = cast(func.floor(numeric / literal(256)), BigInteger)
    byte2 = cast(func.floor(numeric / literal(65536)), BigInteger)
    byte3 = cast(func.floor(numeric / literal(16777216)), BigInteger)
    swapped = (numeric % 256) * 16777216 + (byte1 % 256) * 65536 + (byte2 % 256) * 256 + byte3
    canonical = case((numeric <= swapped, numeric), else_=swapped)
    # Return SQL text because local assignment/event identity columns are text.
    return case((valid, cast(canonical, String)), else_=None)


def reader_id_is_valid(value: str) -> bool:
    try:
        rfid_candidates(value)
        return True
    except (TypeError, ValueError):
        return False


def rfid_equivalence_key(reader_id: str) -> str:
    """Canonical equivalence class shared by active assignments and events."""
    digits = str(reader_id)
    rfid_candidates(digits)
    number = int(digits)
    swapped = int.from_bytes(number.to_bytes(4, "big"), "little")
    return str(min(number, swapped))
