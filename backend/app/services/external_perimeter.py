"""Read-only Arganda SECURITY_DB presence adapter.

The SQL Server connection is configured exclusively through a local secret file.
Never include employee names, PINs or database credentials in API responses.
"""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from app.core.config import settings

SQL = """
SELECT TOP (1) t.event_time, t.acc_zone_code
FROM dbo.pers_attribute_ext AS pae
JOIN dbo.pers_person AS p ON p.id = pae.person_id
JOIN dbo.pers_card AS pc ON pc.person_id = p.id
JOIN dbo.acc_transaction AS t ON t.card_no = pc.card_no
WHERE pae.attr_value4 = ? AND t.acc_zone_code IN (1, 2)
ORDER BY t.event_time DESC, t.log_id DESC
"""


def reader_number_to_attr_value(card: str) -> str:
    digits = card.strip()
    if not digits or not digits.isascii() or not digits.isdecimal():
        raise ValueError("Badge must contain ASCII decimal digits")
    number = int(digits)
    if number >= 2 ** 32:
        raise ValueError("Badge exceeds the validated 32-bit reader format")
    return str(int.from_bytes(number.to_bytes(4, "big"), "little"))


def _connection_string() -> str:
    path = Path(settings.perimeter_sqlserver_credentials_file)
    if not path.is_file():
        raise RuntimeError("External perimeter credentials file is unavailable")
    data = json.loads(path.read_text(encoding="utf-8"))
    # Accept the local ODBC configuration without ever logging its values.
    if "connection_string" in data:
        raise RuntimeError("Use structured SQL credentials; arbitrary ODBC connection strings are not accepted")
    server = data.get("server") or data.get("host")
    database = data.get("database", "SECURITY_DB")
    username = data.get("username") or data.get("user") or data.get("uid")
    password = data.get("password") or data.get("pwd")
    if not all((server, database, username, password)):
        raise RuntimeError("External perimeter connection configuration is incomplete")
    # Escape ODBC values to prevent semicolon injection in credentials.
    def quote(value: str) -> str:
        return "{" + str(value).replace("}", "}}") + "}"
    return (f"DRIVER={{ODBC Driver 18 for SQL Server}};SERVER={quote(server)};"
            f"DATABASE={quote(database)};UID={quote(username)};PWD={quote(password)};"
            f"Encrypt=yes;TrustServerCertificate=yes;Connection Timeout=3;ApplicationIntent=ReadOnly")


def check_external_presence(badge: str, *, now: datetime | None = None, query=None) -> dict:
    """Return INSIDE, OUTSIDE, STALE, UNKNOWN or ERROR; fail closed upstream."""
    try:
        converted = reader_number_to_attr_value(badge)
    except ValueError:
        return {"status": "UNKNOWN", "event_time": None}
    if query is None:
        try:
            import pyodbc
            connection = pyodbc.connect(_connection_string(), timeout=3, autocommit=True)
            try:
                cursor = connection.cursor()
                cursor.execute(SQL, converted)
                row = cursor.fetchone()
            finally:
                connection.close()
        except Exception:
            return {"status": "ERROR", "event_time": None}
    else:
        try:
            row = query(converted)
        except Exception:
            return {"status": "ERROR", "event_time": None}
    if row is None:
        return {"status": "UNKNOWN", "event_time": None}
    event_time, raw_zone_code = row[0], row[1]
    # SECURITY_DB stores acc_zone_code as nvarchar; ODBC therefore returns
    # "1"/"2" rather than integers. Reject malformed values as UNKNOWN.
    try:
        zone_code = int(raw_zone_code)
    except (TypeError, ValueError):
        return {"status": "UNKNOWN", "event_time": None}
    if event_time is None or zone_code not in (1, 2):
        return {"status": "UNKNOWN", "event_time": None}
    if event_time.tzinfo is None:
        event_time = event_time.replace(tzinfo=ZoneInfo(settings.event_timezone))
    current = now or datetime.now(timezone.utc)
    age = current.astimezone(timezone.utc) - event_time.astimezone(timezone.utc)
    if age < timedelta(seconds=-60):
        return {"status": "ERROR", "event_time": None}
    status = "OUTSIDE" if zone_code == 1 else ("STALE" if age > timedelta(hours=settings.perimeter_external_max_age_hours) else "INSIDE")
    return {"status": status, "event_time": event_time.isoformat()}
