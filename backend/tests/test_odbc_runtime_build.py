from pathlib import Path
import hashlib
import re

BACKEND_DIR = Path(__file__).resolve().parents[1]
ROOT_DIR = BACKEND_DIR.parent
DOCKERFILES = (BACKEND_DIR / "Dockerfile.corp-offline", BACKEND_DIR / "Dockerfile.corp-offline-recovery")
DRIVER = "ODBC Driver 18 for SQL Server"


def test_corporate_runtime_dockerfiles_install_verified_odbc_stack():
    for dockerfile in DOCKERFILES:
        source = dockerfile.read_text()
        assert "COPY odbc-packages /tmp/odbc-packages" in source, dockerfile.name
        assert "sha256sum -c MANIFEST.txt" in source, dockerfile.name
        assert "dpkg -i ./*.deb" in source, dockerfile.name
        assert "pyodbc-5.2.0-cp312-cp312" in source, dockerfile.name
        assert "import pyodbc" in source, dockerfile.name
        assert DRIVER in source, dockerfile.name
        assert "odbcinst -q -d -n" in source, dockerfile.name
        assert "libodbc.so.2" in source, dockerfile.name
        assert "pyodbc.drivers()" in source, dockerfile.name


def test_offline_manifest_pins_required_runtime_packages():
    package_dir = BACKEND_DIR / "odbc-packages"
    entries = {}
    for line in (package_dir / "MANIFEST.txt").read_text().splitlines():
        digest, filename = line.split(maxsplit=1)
        entries[filename.strip()] = digest
    assert any(name.startswith("msodbcsql18_") for name in entries)
    assert any(name.startswith("libodbc2_") for name in entries)
    assert any(name.startswith("libodbcinst2_") for name in entries)
    assert any(name.startswith("unixodbc_") for name in entries)
    assert any(name.startswith("pyodbc-5.2.0-") for name in entries)
    assert all(re.fullmatch(r"[0-9a-f]{64}", digest) for digest in entries.values())
    for filename, expected_digest in entries.items():
        artifact = package_dir / filename
        if artifact.exists():
            assert hashlib.sha256(artifact.read_bytes()).hexdigest() == expected_digest


def test_recovery_api_and_worker_share_one_runtime_image():
    compose = (ROOT_DIR / "docker-compose.odbc-recovery.yml").read_text()
    assert compose.count("bsstimecollection-api:${BSS_API_REVISION") == 2
    assert compose.count("dockerfile: Dockerfile.corp-offline-recovery") == 1
    assert compose.count("context: ./backend") == 1
    assert 'command: ["python", "-m", "app.worker"]' in compose
