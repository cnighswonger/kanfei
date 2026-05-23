"""CWOP service-state endpoints.

Exposes the list of CWOP channels the operator has muted so the UI can
keep a persistent reminder banner up while any sensor is taken out of
service.  Auth-gated: on installations where the dashboard is exposed
publicly we don't want to leak operator maintenance state to anonymous
visitors.  The banner therefore renders for logged-in operators only,
which is the audience for the reminder anyway.

The actual mute toggles are written through the admin ``/api/config`` PUT
under the ``cwop_mute_<channel>`` keys; this module only reads.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..models.auth import UserModel
from ..models.database import get_db
from ..models.station_config import StationConfigModel
from ..services.cwop import CWOP_MUTE_CHANNELS, _mute_key
from .dependencies import optional_auth


router = APIRouter(prefix="/cwop", tags=["cwop"])


@router.get("/mute-status")
def get_mute_status(
    db: Session = Depends(get_db),
    user: UserModel | None = Depends(optional_auth),
) -> dict:
    """Return the list of CWOP channel ids the operator has currently muted.

    Returns an empty ``muted`` list for unauthenticated callers so the
    public dashboard does not leak the station's maintenance state.  The
    reminder banner is intended for the operator, who is logged in.
    """
    if user is None:
        return {"muted": []}
    keys = [_mute_key(c) for c in CWOP_MUTE_CHANNELS]
    rows = db.query(StationConfigModel).filter(StationConfigModel.key.in_(keys)).all()
    on = {r.key for r in rows if str(r.value).lower() == "true"}
    return {"muted": [c for c in CWOP_MUTE_CHANNELS if _mute_key(c) in on]}
