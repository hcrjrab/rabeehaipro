"""API route modules.

Each module exposes a ``router: APIRouter`` and is mounted by the app
factory. Keeping them split per concern keeps diffs small and lets the
OpenAPI docs group endpoints logically.
"""

from __future__ import annotations
