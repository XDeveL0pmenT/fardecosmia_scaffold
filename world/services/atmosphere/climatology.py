"""Shared baseline atmospheric climatology helpers.

These values initialize the prognostic atmosphere.  They are technical,
configurable starting conditions rather than additional biome lore.
"""

from __future__ import annotations

import numpy as np


def initial_relative_humidity_percent(is_ocean, settings):
    """Return the configured initial RH field for a surface mask."""

    ocean_mask = np.asarray(is_ocean, dtype=np.bool_)
    return np.where(
        ocean_mask,
        settings.value("initial_ocean_humidity"),
        settings.value("initial_land_humidity"),
    )
