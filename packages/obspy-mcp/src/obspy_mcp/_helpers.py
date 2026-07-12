"""Self-contained helpers for obspy-mcp.

Deliberately inlined (rather than depending on a shared ``seismo-mcp-core``
package) so this server can be published to PyPI and installed standalone
via ``uvx obspy-mcp`` with no companion package. The ~100 lines here are the
cost of that independence — a worthwhile trade for zero-friction install.

If other seismo-mcp servers grow up alongside this one, they each carry
their own copy of the bits they need; duplication is cheap, coupling is not.
"""

from __future__ import annotations

import io
import os
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # headless; must precede any pyplot use
import matplotlib.pyplot as plt

# 2 MB soft cap — bigger plots should go to a file, not inline base64.
_INLINE_MAX_BYTES = 2 * 1024 * 1024


def figure_to_image(fig, *, format: str = "png", dpi: int = 100, max_bytes: int = _INLINE_MAX_BYTES):
    """Render *fig* to a FastMCP ``Image`` for inline return from a tool.

    Raises ValueError if the rendered PNG exceeds ``max_bytes`` — callers
    should then fall back to :func:`save_figure`.
    """
    buf = io.BytesIO()
    fig.savefig(buf, format=format, dpi=dpi, bbox_inches="tight")
    plt.close(fig)
    data = buf.getvalue()
    if len(data) > max_bytes:
        raise ValueError(
            f"Rendered image is {len(data)} bytes (> {max_bytes}); "
            "use save_figure() to write to a file and return the path instead."
        )
    from mcp.server.fastmcp import Image
    return Image(data=data, format=format)


def save_figure(fig, output_path: str | Path, *, format: str = "png", dpi: int = 100) -> str:
    """Write *fig* to *output_path* and return the absolute path string."""
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, format=format, dpi=dpi, bbox_inches="tight")
    plt.close(fig)
    return str(out.resolve())


def probe_obspy() -> str:
    """Return a one-line status string: importable + version, or the error."""
    try:
        import obspy
        return f"OK: ObsPy {obspy.__version__} importable"
    except Exception as exc:  # ImportError or env-level failure
        return (f"ERROR: ObsPy is not importable. Install it in the server's "
                f"environment first.\nDetail: {exc}")
