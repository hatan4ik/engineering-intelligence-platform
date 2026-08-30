"""Operational-intelligence application boundary.

The public modules separate input normalization, capability composition,
presentation, publishing, and HTTP transport.  ``app.operations_api`` remains
a compatibility façade for existing scripts and integrations.
"""

from .routes import router

__all__ = ["router"]
