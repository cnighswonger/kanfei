"""Backup and restore API endpoints."""

import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
from pydantic import BaseModel

from ..config import settings
from ..services.backup import (
    create_backup,
    restore_backup,
    list_backups,
    get_backup_dir,
    generate_backup_filename,
    rotate_backups,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/backup", tags=["backup"])


class RestoreRequest(BaseModel):
    confirmation: str  # must be "RESTORE"


@router.post("")
def trigger_backup():
    """Create a backup immediately. Returns manifest."""
    try:
        backup_dir = get_backup_dir(settings.db_path)
        filename = generate_backup_filename()
        output = str(Path(backup_dir) / filename)
        manifest = create_backup(settings.db_path, output)

        # Rotate after manual backup too
        from ..models.database import SessionLocal
        from ..models.station_config import StationConfigModel
        db = SessionLocal()
        try:
            row = db.query(StationConfigModel).filter_by(key="backup_retention_count").first()
            keep = int(row.value) if row else 7
        finally:
            db.close()
        rotate_backups(backup_dir, keep=keep)

        return manifest
    except Exception as exc:
        logger.error("Backup failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/list")
def get_backups():
    """List existing backups."""
    backup_dir = get_backup_dir(settings.db_path)
    return list_backups(backup_dir)


@router.get("/download/{name}")
def download_backup(name: str):
    """Download a backup archive by name."""
    # Sanitize filename — prevent path traversal
    if "/" in name or "\\" in name or ".." in name:
        raise HTTPException(status_code=400, detail="Invalid filename")

    backup_dir = get_backup_dir(settings.db_path)
    path = Path(backup_dir) / name

    if not path.exists() or not path.name.startswith("kanfei-backup-"):
        raise HTTPException(status_code=404, detail="Backup not found")

    return FileResponse(
        path=str(path),
        filename=name,
        media_type="application/gzip",
    )


@router.post("/restore")
async def restore_from_upload(
    confirmation: str,
    file: UploadFile = File(...),
):
    """Restore from an uploaded backup archive.

    Requires confirmation="RESTORE" to proceed.
    """
    if confirmation != "RESTORE":
        raise HTTPException(
            status_code=400,
            detail='Confirmation required: set confirmation="RESTORE"',
        )

    if not file.filename or not file.filename.endswith(".tar.gz"):
        raise HTTPException(status_code=400, detail="File must be a .tar.gz archive")

    # Save upload to temp location
    backup_dir = get_backup_dir(settings.db_path)
    Path(backup_dir).mkdir(parents=True, exist_ok=True)
    upload_path = Path(backup_dir) / f"_upload_{file.filename}"

    try:
        content = await file.read()
        upload_path.write_bytes(content)

        target_dir = str(Path(settings.db_path).parent)
        manifest = restore_backup(str(upload_path), target_dir)

        return {"status": "restored", "manifest": manifest}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.error("Restore failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))
    finally:
        if upload_path.exists():
            upload_path.unlink()


@router.delete("/{name}")
def delete_backup(name: str):
    """Delete a backup archive."""
    if "/" in name or "\\" in name or ".." in name:
        raise HTTPException(status_code=400, detail="Invalid filename")

    backup_dir = get_backup_dir(settings.db_path)
    path = Path(backup_dir) / name

    if not path.exists() or not path.name.startswith("kanfei-backup-"):
        raise HTTPException(status_code=404, detail="Backup not found")

    path.unlink()
    return {"status": "deleted", "name": name}
