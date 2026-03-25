"""Ambient Weather / Fine Offset HTTP push driver package.

Supports any weather station that pushes data via the Wunderground or
Ecowitt HTTP protocol: Ambient Weather, Ecowitt (push mode), Froggit,
Sainlogic, Misol, and other Fine Offset OEM devices.
"""

from .driver import AmbientDriver

__all__ = ["AmbientDriver"]
