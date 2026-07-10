"""Backup and restore: PostgreSQL dump, sites archive, manifest with checksums."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from app.config import settings

logger = __import__("logging").getLogger(__name__)


def _hash_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def create_backup(output_dir: str | Path) -> dict:
    """Create a full backup: pg_dump + sites archive + manifest.

    Secrets are NOT included in the backup.
    Returns manifest dict with paths, checksums, revision, and timestamp.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    revision = _get_alembic_revision()

    manifest: dict = {
        "timestamp": timestamp,
        "alembic_revision": revision,
        "database_url_hash": _hash_bytes(settings.database_url.encode()),
        "files": {},
    }

    pg_dump_path = output_dir / f"pg_dump_{timestamp}.sql"
    _run_pg_dump(pg_dump_path)
    if pg_dump_path.exists():
        manifest["files"]["pg_dump"] = {
            "path": pg_dump_path.name,
            "sha256": _hash_file(pg_dump_path),
            "size": pg_dump_path.stat().st_size,
        }

    sites_archive_path = output_dir / f"sites_{timestamp}.tar.gz"
    _archive_sites(sites_archive_path)
    if sites_archive_path.exists():
        manifest["files"]["sites_archive"] = {
            "path": sites_archive_path.name,
            "sha256": _hash_file(sites_archive_path),
            "size": sites_archive_path.stat().st_size,
        }

    manifest_path = output_dir / f"manifest_{timestamp}.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    manifest["files"]["manifest"] = {
        "path": manifest_path.name,
        "sha256": _hash_file(manifest_path),
    }

    return manifest


def verify_backup(backup_dir: str | Path) -> tuple[bool, list[str]]:
    """Verify backup integrity: check checksums and manifest structure.

    Returns (is_valid, list_of_errors).
    """
    backup_dir = Path(backup_dir)
    errors: list[str] = []

    manifests = sorted(backup_dir.glob("manifest_*.json"))
    if not manifests:
        errors.append("No manifest file found")
        return False, errors

    manifest_path = manifests[-1]
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        errors.append(f"Failed to parse manifest: {exc}")
        return False, errors

    required_keys = ["timestamp", "alembic_revision", "files"]
    for key in required_keys:
        if key not in manifest:
            errors.append(f"Missing key in manifest: {key}")

    for file_key, file_info in manifest.get("files", {}).items():
        file_path = backup_dir / file_info["path"]
        if not file_path.exists():
            errors.append(f"File referenced in manifest not found: {file_info['path']}")
            continue
        actual_hash = _hash_file(file_path)
        if actual_hash != file_info["sha256"]:
            errors.append(f"Checksum mismatch for {file_info['path']}: expected {file_info['sha256']}, got {actual_hash}")

    return len(errors) == 0, errors


def restore_database(backup_dir: str | Path, target_database_url: str) -> dict:
    """Restore PostgreSQL database from pg_dump file into target_database_url.

    Returns {"success": bool, "message": str}.
    """
    backup_dir = Path(backup_dir)
    manifests = sorted(backup_dir.glob("manifest_*.json"))
    if not manifests:
        return {"success": False, "message": "No manifest found"}

    manifest = json.loads(manifests[-1].read_text(encoding="utf-8"))
    pg_dump_info = manifest.get("files", {}).get("pg_dump")
    if not pg_dump_info:
        return {"success": False, "message": "No pg_dump in manifest"}

    dump_path = backup_dir / pg_dump_info["path"]
    if not dump_path.exists():
        return {"success": False, "message": f"Dump file not found: {dump_path}"}

    try:
        result = subprocess.run(
            ["psql", target_database_url, "-f", str(dump_path)],
            capture_output=True,
            text=True,
            timeout=300,
        )
        if result.returncode != 0:
            return {"success": False, "message": f"psql failed: {result.stderr[:500]}"}
        return {"success": True, "message": "Database restored successfully"}
    except FileNotFoundError:
        return {"success": False, "message": "psql not found — install postgresql-client"}
    except subprocess.TimeoutExpired:
        return {"success": False, "message": "Restore timed out"}


def _run_pg_dump(output_path: Path) -> None:
    """Run pg_dump to the output file. Secrets are not included."""
    url = settings.database_url
    try:
        result = subprocess.run(
            ["pg_dump", url, "-f", str(output_path), "--no-owner", "--no-privileges"],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            logger.warning("pg_dump failed: %s", result.stderr[:300])
    except FileNotFoundError:
        logger.warning("pg_dump not found — install postgresql-client")
    except subprocess.TimeoutExpired:
        logger.warning("pg_dump timed out")


def _archive_sites(output_path: Path) -> None:
    """Create tar.gz archive of sites/public directory."""
    sites_dir = Path("sites/public")
    if not sites_dir.exists():
        logger.info("sites/public does not exist, skipping archive")
        return
    with tarfile.open(output_path, "w:gz") as tar:
        tar.add(str(sites_dir), arcname="sites/public")


def _get_alembic_revision() -> str | None:
    """Get current alembic head revision."""
    try:
        from alembic.config import Config
        from alembic.script import ScriptDirectory
        config = Config("alembic.ini")
        script = ScriptDirectory.from_config(config)
        heads = script.get_heads()
        return heads[0] if heads else None
    except Exception:
        return None
