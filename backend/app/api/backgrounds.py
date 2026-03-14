"""Custom background image management API.

GET    /api/backgrounds          - List which scenes have custom images
POST   /api/backgrounds/{scene}  - Upload image for a scene
DELETE /api/backgrounds/{scene}  - Remove custom image for a scene

Images served via static mount at /backgrounds/.
"""

import logging
from pathlib import Path

from fastapi import APIRouter, UploadFile, File, HTTPException

logger = logging.getLogger(__name__)
router = APIRouter()

VALID_SCENES = {
    "clear-day", "clear-night", "dawn", "dusk",
    "rain", "rain-night", "storm", "snow",
}

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB

# Set by main.py at startup
_backgrounds_dir: Path | None = None


def set_backgrounds_dir(path: Path):
    global _backgrounds_dir
    _backgrounds_dir = path
    path.mkdir(parents=True, exist_ok=True)


def _find_scene_file(scene: str) -> Path | None:
    """Find existing file for a scene (any allowed extension)."""
    if _backgrounds_dir is None:
        return None
    for ext in ALLOWED_EXTENSIONS:
        p = _backgrounds_dir / f"{scene}{ext}"
        if p.exists():
            return p
    return None


@router.get("/backgrounds")
def list_backgrounds():
    """List which scenes have custom images."""
    scenes = {}
    if _backgrounds_dir is not None:
        for scene in VALID_SCENES:
            f = _find_scene_file(scene)
            if f is not None:
                scenes[scene] = f.name
    return {"scenes": scenes}


@router.post("/backgrounds/{scene}")
async def upload_background(scene: str, file: UploadFile = File(...)):
    """Upload a custom background image for a scene."""
    if scene not in VALID_SCENES:
        raise HTTPException(status_code=400, detail=f"Invalid scene: {scene}")
    if _backgrounds_dir is None:
        raise HTTPException(status_code=500, detail="Backgrounds directory not configured")

    # Validate content type
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type. Allowed: {', '.join(ALLOWED_EXTENSIONS)}",
        )

    # Read and validate size
    data = await file.read()
    if len(data) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="File too large (max 5MB)")

    # Remove any existing file for this scene
    existing = _find_scene_file(scene)
    if existing is not None:
        existing.unlink()

    # Save new file
    dest = _backgrounds_dir / f"{scene}{ext}"
    dest.write_bytes(data)
    logger.info("Background uploaded: %s (%d bytes)", dest.name, len(data))

    return {"success": True, "filename": dest.name}


@router.delete("/backgrounds/{scene}")
def delete_background(scene: str):
    """Remove custom background image for a scene."""
    if scene not in VALID_SCENES:
        raise HTTPException(status_code=400, detail=f"Invalid scene: {scene}")

    existing = _find_scene_file(scene)
    if existing is not None:
        existing.unlink()
        logger.info("Background removed: %s", existing.name)
        return {"success": True}

    return {"success": False, "detail": "No custom image for this scene"}
