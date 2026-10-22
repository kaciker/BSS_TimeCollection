"""Read-only Arganda SECURITY_DB presence adapter.

The SQL Server connection is configured exclusively through a local secret file.
Never include employee names, PINs or database credentials in API responses.
"""
import json
import logging
import re
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

logger = logging.getLogger(__name__)
PROVIDER = "SQLSERVER_SECURITY_DB"
DRIVER = "ODBC Driver 18 for SQL Server"
_last_check: dict = {"last_check_at": None, "status": "NOT_CHECKED", "reachable": False, "error_category": None}


def reader_number_to_attr_value(card: str) -> str:
    digits = card.strip()
    if not digits or not digits.isascii() or not digits.isdecimal():
        raise ValueError("Badge must contain ASCII decimal digits")
    number = int(digits)
    if number >= 2 ** 32:
        raise ValueError("Badge exceeds the validated 32-bit reader format")
    return str(int.from_bytes(number.to_bytes(4, "big"), "little"))


class ExternalPerimeterError(RuntimeError):
    def __init__(self, category: str):
        super().__init__(category)
        self.category = category


def _credentials() -> dict:
    path = Path(settings.perimeter_sqlserver_credentials_file)
    if not path.is_file():
        raise ExternalPerimeterError("CREDENTIALS_UNAVAILABLE")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise ExternalPerimeterError("CREDENTIALS_UNAVAILABLE") from None
    if not isinstance(data, dict):
        raise ExternalPerimeterError("CREDENTIALS_UNAVAILABLE")
    # Accept the local ODBC configuration without ever logging its values.
    if "connection_string" in data:
        raise ExternalPerimeterError("CREDENTIALS_UNAVAILABLE")
    server = data.get("server") or data.get("host")
    database = data.get("database", "SECURITY_DB")
    username = data.get("username") or data.get("user") or data.get("uid")
    password = data.get("password") or data.get("pwd")
    if not all((server, database, username, password)):
        raise ExternalPerimeterError("CREDENTIALS_UNAVAILABLE")
    return {"server": str(server), "database": str(database), "username": str(username), "password": str(password)}


def _connection_string(data: dict | None = None) -> str:
    data = data or _credentials()
    server = data["server"]
    database = data["database"]
    username = data["username"]
    password = data["password"]
    # Escape ODBC values to prevent semicolon injection in credentials.
    def quote(value: str) -> str:
        return "{" + str(value).replace("}", "}}") + "}"
    return (f"DRIVER={{{DRIVER}}};SERVER={quote(server)};"
            f"DATABASE={quote(database)};UID={quote(username)};PWD={quote(password)};"
            f"Encrypt=yes;TrustServerCertificate=yes;Connection Timeout=3;ApplicationIntent=ReadOnly")


def _safe_odbc_category(exc: Exception, *, phase: str) -> str:
    # Inspect only enough of the driver diagnostic to classify it. Never return or log
    # the original message because ODBC errors may contain server or login details.
    diagnostic = " ".join(str(part) for part in getattr(exc, "args", ())).lower()
    if "im002" in diagnostic or "driver" in diagnostic and ("not found" in diagnostic or "not exist" in diagnostic or "can't open lib" in diagnostic or "cannot open lib" in diagnostic):
        return "ODBC_DRIVER_UNAVAILABLE"
    if any(code in diagnostic for code in ("28000", "18456", "login failed", "authentication failed")):
        return "AUTH_FAILED"
    return "CONNECTION_FAILED" if phase == "connect" else "QUERY_FAILED"


def connector_status(*, check: bool = False, connect=None) -> dict:
    """Return a credential-free connector status; optionally perform read-only SELECT 1."""
    try:
        config = _credentials()
    except ExternalPerimeterError:
        result = {"provider": PROVIDER, "configured": False, "reachable": False,
                  "database": "SECURITY_DB", "server": None, "driver": DRIVER,
                  "last_check_at": _last_check["last_check_at"], "status": "NOT_CONFIGURED",
                  "error_category": "CREDENTIALS_UNAVAILABLE"}
        if check:
            _last_check.update({"last_check_at": datetime.now(timezone.utc).isoformat(),
                                "status": result["status"], "reachable": False,
                                "error_category": result["error_category"]})
            result.update(_last_check)
        return result
    server = config["server"]
    # Only expose conventional host/port values, never arbitrary connection fragments.
    safe_server = server if re.fullmatch(r"[A-Za-z0-9._:\[\]-]{1,255}", server) else None
    safe_database = config["database"] if re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", config["database"]) else None
    result = {"provider": PROVIDER, "configured": True, "reachable": False,
              "database": safe_database, "server": safe_server, "driver": DRIVER,
              "last_check_at": _last_check["last_check_at"], "status": _last_check["status"],
              "error_category": _last_check["error_category"]}
    if not check:
        result.update(_last_check)
        return result
    now = datetime.now(timezone.utc).isoformat()
    phase = "connect"
    connection = None
    try:
        if connect is None:
            try:
                import pyodbc
            except ImportError:
                raise ExternalPerimeterError("ODBC_DRIVER_UNAVAILABLE") from None
            connect = pyodbc.connect
        connection = connect(_connection_string(config), timeout=3, autocommit=True)
        phase = "query"
        try:
            connection.cursor().execute("SELECT 1").fetchone()
        finally:
            connection.close()
        _last_check.update({"last_check_at": now, "status": "CONNECTED", "reachable": True, "error_category": None})
    except ExternalPerimeterError as exc:
        _last_check.update({"last_check_at": now, "status": "ERROR", "reachable": False, "error_category": exc.category})
    except Exception as exc:
        category = _safe_odbc_category(exc, phase=phase)
        logger.warning("Arganda external perimeter connection check failed (%s)", category)
        _last_check.update({"last_check_at": now, "status": "ERROR", "reachable": False, "error_category": category})
    result.update(_last_check)
    return result


def test_external_connection(*, connect=None) -> dict:
    """Explicit test operation; records last check even when credentials are absent."""
    result = connector_status(check=True, connect=connect)
    _last_check.update({"last_check_at": datetime.now(timezone.utc).isoformat(),
                        "status": "NOT_CONFIGURED", "reachable": False,
                        "error_category": "CREDENTIALS_UNAVAILABLE"}) if not result["configured"] else None
    result.update(_last_check)
    return result


def check_external_presence(badge: str, *, now: datetime | None = None, query=None) -> dict:
    """Return INSIDE, OUTSIDE, STALE, UNKNOWN or ERROR; fail closed upstream."""
    try:
        converted = reader_number_to_attr_value(badge)
    except ValueError:
        return {"status": "UNKNOWN", "event_time": None, "zone_code": None, "error_category": "INVALID_RESPONSE"}
    if query is None:
        connection = None
        try:
            config = _credentials()
            import pyodbc
            connection = pyodbc.connect(_connection_string(config), timeout=3, autocommit=True)
            try:
                cursor = connection.cursor()
                cursor.execute(SQL, converted)
                row = cursor.fetchone()
            finally:
                connection.close()
        except ExternalPerimeterError as exc:
            return {"status": "ERROR", "event_time": None, "zone_code": None, "error_category": exc.category}
        except ImportError:
            return {"status": "ERROR", "event_time": None, "zone_code": None, "error_category": "ODBC_DRIVER_UNAVAILABLE"}
        except Exception as exc:
            category = _safe_odbc_category(exc, phase="connect" if connection is None else "query")
            logger.warning("Arganda external presence lookup failed (%s)", category)
            return {"status": "ERROR", "event_time": None, "zone_code": None, "error_category": category}
    else:
        try:
            row = query(converted)
        except Exception:
            return {"status": "ERROR", "event_time": None, "zone_code": None, "error_category": "QUERY_FAILED"}
    if row is None:
        return {"status": "UNKNOWN", "event_time": None, "zone_code": None, "error_category": None}
    try:
        event_time, raw_zone_code = row[0], row[1]
    except (TypeError, IndexError, KeyError):
        return {"status": "UNKNOWN", "event_time": None, "zone_code": None, "error_category": "INVALID_RESPONSE"}
    # SECURITY_DB stores acc_zone_code as nvarchar; ODBC therefore returns
    # "1"/"2" rather than integers. Reject malformed values as UNKNOWN.
    try:
        zone_code = int(raw_zone_code)
    except (TypeError, ValueError):
        return {"status": "UNKNOWN", "event_time": None, "zone_code": None, "error_category": "INVALID_RESPONSE"}
    if event_time is None or zone_code not in (1, 2):
        return {"status": "UNKNOWN", "event_time": None, "zone_code": zone_code if zone_code in (1, 2) else None, "error_category": "INVALID_RESPONSE"}
    if not isinstance(event_time, datetime):
        return {"status": "UNKNOWN", "event_time": None, "zone_code": zone_code, "error_category": "INVALID_RESPONSE"}
    if event_time.tzinfo is None:
        event_time = event_time.replace(tzinfo=ZoneInfo(settings.event_timezone))
    current = now or datetime.now(timezone.utc)
    age = current.astimezone(timezone.utc) - event_time.astimezone(timezone.utc)
    if age < timedelta(seconds=-60):
        return {"status": "ERROR", "event_time": None, "zone_code": zone_code, "error_category": "INVALID_RESPONSE"}
    status = "OUTSIDE" if zone_code == 1 else ("STALE" if age > timedelta(hours=settings.perimeter_external_max_age_hours) else "INSIDE")
    return {"status": status, "event_time": event_time.isoformat(), "zone_code": zone_code, "error_category": None}
