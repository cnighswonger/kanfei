"""Public CWOP service-state endpoints.

Exposes a tiny, no-auth read of which CWOP channels the operator has muted.
The UI uses this to keep a persistent reminder banner up while any sensor is
taken out of service.

The actual mute toggles are written through the admin ``/api/config`` PUT
under the ``cwop_mute_<channel>`` keys; this module only reads.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..models.database import get_db
from ..models.station_config import StationConfigModel
from ..services.cwop import CWOP_MUTE_CHANNELS, _mute_key


router = APIRouter(prefix="/cwop", tags=["cwop"])


@router.get("/mute-status")
def get_mute_status(db: Session = Depends(get_db)) -> dict:
    """Return the list of CWOP channel ids the operator has currently muted.

    Public — no auth required.  Used by the AppShell to display a persistent
    reminder banner whenever any channel is being suppressed from the APRS
    WX packet.
    """
    keys = [_mute_key(c) for c in CWOP_MUTE_CHANNELS]
    rows = db.query(StationConfigModel).filter(StationConfigModel.key.in_(keys)).all()
    on = {r.key for r in rows if str(r.value).lower() == "true"}
    return {"muted": [c for c in CWOP_MUTE_CHANNELS if _mute_key(c) in on]}
