"""Compact, deterministic prototype atmosphere for Fardecosmia."""

from .config import AtmosphericSettings
from .grid import AtmosphericGrid
from .simulation import initialize_atmosphere, simulate_step

__all__ = [
    "AtmosphericGrid",
    "AtmosphericSettings",
    "initialize_atmosphere",
    "simulate_step",
]
