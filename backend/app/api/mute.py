"""Per-channel mute state endpoint.

Exposes the list of channels the operator has currently muted so the UI
can keep a persistent reminder banner up while any sensor is taken out
of service.  Auth-gated: on installations where the dashboard is exposed
publicly we don't want to leak operator maintenance state to anonymous
visitors.  The banner therefore renders for logged-in operators only,
which is the audience for the reminder anyway.

The actual mute toggles are written through the admin ``/api/config``
PUT under the ``channel_mute_<channel>`` keys; this module only reads.
The mute set is service-agnostic — every outbound upload (CWOP/APRS,
Weather Underground, future destinations) consults it (issue #162).
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..models.auth import UserModel
from ..models.database import get_db
from ..services.channel_mute import MUTE_CHANNELS, load_muted_channels
from .dependencies import optional_auth


router = APIRouter(prefix="/mute", tags=["mute"])


@router.get("/status")
def get_mute_status(
    db: Session = Depends(get_db),
    user: UserModel | None = Depends(optional_auth),
) -> dict:
    """Return the list of channel ids the operator has currently muted.

    Returns an empty ``muted`` list for unauthenticated callers so the
    public dashboard does not leak the station's maintenance state.  The
    reminder banner is intended for the operator, who is logged in.

    Channel ids are returned in the canonical ``MUTE_CHANNELS`` order.
    """
    if user is None:
        return {"muted": []}
    muted = load_muted_channels(db)
    return {"muted": [c for c in MUTE_CHANNELS if c in muted]}
