"""Self-contained helpers for gmt-mcp.

Inlined (no shared-package dependency) so this server publishes and installs
standalone via ``uvx gmt-mcp``.

PyGMT needs the GMT C binary on PATH — that's the one external requirement
that can't be pip-installed. :func:`probe_pygmt` checks both that the Python
module imports AND that the underlying ``gmt`` binary is reachable, because
PyGMT raises a cryptic error at first plot if the binary is missing.

:func:`figure_to_image` / :func:`save_figure` are the same headless-render
pattern used by the sibling obspy-mcp: render to PNG, inline if small,
otherwise write to a file and return the path.
"""

from __future__ import annotations

import io
import os
import shutil
from pathlib import Path

# PNGs from GMT can be large (maps with coastlines); keep the inline cap
# modest so we don't bloat the model context.
_INLINE_MAX_BYTES = 2 * 1024 * 1024


def probe_pygmt() -> str:
    """One-line status: PyGMT importable + GMT binary on PATH, or the error."""
    try:
        import pygmt
        version = pygmt.__version__
    except Exception as exc:
        return (f"ERROR: PyGMT not importable. Install it (and the GMT binary) "
                f"first.\nDetail: {exc}")
    # PyGMT needs the gmt binary; check it explicitly so the error message is
    # actionable rather than PyGMT's deferred crash.
    if shutil.which("gmt") is None:
        return (f"ERROR: PyGMT {version} imports, but the 'gmt' binary is NOT "
                f"on PATH. PyGMT needs GMT installed separately "
                f"(e.g. `brew install gmt` on macOS).")
    return f"OK: PyGMT {version} importable, GMT binary on PATH"


def figure_to_image(png_bytes: bytes, *, max_bytes: int = _INLINE_MAX_BYTES):
    """Wrap already-rendered PNG *bytes* as a FastMCP inline Image.

    Raises ValueError if the PNG exceeds ``max_bytes`` — caller should then
    write it to a file via :func:`save_figure` and return the path.
    """
    if len(png_bytes) > max_bytes:
        raise ValueError(
            f"Rendered image is {len(png_bytes)} bytes (> {max_bytes}); "
            "write it to a file and return the path instead."
        )
    from mcp.server.fastmcp import Image
    return Image(data=png_bytes, format="png")


def save_figure(png_bytes: bytes, output_path: str | Path) -> str:
    """Write *png_bytes* to *output_path*; return the absolute path string."""
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(png_bytes)
    return str(out.resolve())


def render_fig_to_png(fig, *, dpi: int = 150) -> bytes:
    """Render a PyGMT Figure to PNG bytes (via a temp file)."""
    tmp = "/tmp/_gmt_mcp_render.png"
    fig.savefig(tmp, dpi=dpi)
    with open(tmp, "rb") as fh:
        data = fh.read()
    try:
        os.remove(tmp)
    except OSError:
        pass
    return data
