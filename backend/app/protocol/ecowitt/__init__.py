"""Ecowitt / Fine Offset gateway driver package.

Supports Ecowitt GW1000, GW1100, GW2000, HP2551, HP2553, and compatible
gateways/consoles via the TCP binary LAN API on port 45000.

Also covers stations sold under Ambient Weather, Froggit, Sainlogic,
Bresser, and Logia brands (all Fine Offset OEM hardware).
"""

from .driver import EcowittDriver

__all__ = ["EcowittDriver"]
