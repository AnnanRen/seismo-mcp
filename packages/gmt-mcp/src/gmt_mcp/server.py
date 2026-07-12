"""PyGMT MCP server.

Each tool builds a PyGMT Figure, renders it to PNG, and returns either an
inline Image (small plots the model should see) or a file path (large maps).
All tools follow the same shape: build → render → return.

PyGMT's API is a Python wrapping of the GMT command-line modules, so this
server is an *in-process import* wrapper (same pattern as obspy-mcp) — no
subprocess, no shell. The design rule from the sibling servers carries over:
return summaries and image references, never raw data arrays.
"""

from __future__ import annotations

import os
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from ._helpers import probe_pygmt, figure_to_image, save_figure, render_fig_to_png

mcp = FastMCP("gmt-mcp")


# ---------------------------------------------------------------------------
# Tool 1: diagnose_environment
# ---------------------------------------------------------------------------
@mcp.tool()
def diagnose_environment() -> str:
    """Report whether PyGMT is importable and the GMT binary is on PATH.

    Call this first. PyGMT needs BOTH the Python package AND the GMT C binary
    installed (``brew install gmt`` on macOS). Returns a status line."""
    return probe_pygmt()


# ---------------------------------------------------------------------------
# Tool 2: make_basemap — base map with frame and optional coast
# ---------------------------------------------------------------------------
@mcp.tool()
def make_basemap(
    region: list[float],
    projection: str = "M15c",
    *,
    frame: str = "af",
    coast: bool = True,
    land: str = "gray",
    water: str = "lightblue",
    shorelines: str = "1/0.5p,black",
    output_path: str | None = None,
    dpi: int = 150,
) -> str:
    """Draw a base map with an optional coastline, save as PNG.

    *region*: [w, e, s, n] in degrees (e.g. [100, 130, 20, 45] for East Asia).
    *projection*: a GMT projection string (e.g. "M15c" Mercator 15cm wide,
    "Q10/15" equidistant cylindrical, "X10c/8c" Cartesian). *frame*: map
    frame/grid ("af" = auto ticks, "a30f15g15" = 30° ticks/15° grid).
    Set *coast*=False for a plain basemap (faster, no coastline resolution).
    Returns an inline image, or a file path if *output_path* given / image big.
    """
    import pygmt

    fig = pygmt.Figure()
    fig.basemap(region=region, projection=projection, frame=frame)
    if coast:
        fig.coast(land=land, water=water, shorelines=shorelines)
    return _finish(fig, output_path, dpi, f"basemap {region} {projection}")


# ---------------------------------------------------------------------------
# Tool 3: plot_points — plot (lon, lat) points (epicenters, stations, ...)
# ---------------------------------------------------------------------------
@mcp.tool()
def plot_points(
    region: list[float],
    projection: str,
    lons: list[float],
    lats: list[float],
    *,
    style: str = "c0.3c",
    color: str = "red",
    pen: str = "0.5p,black",
    coast: bool = True,
    frame: str = "af",
    output_path: str | None = None,
    dpi: int = 150,
) -> str:
    """Plot points (e.g. epicenters, station locations) on a map.

    *lons*/*lats*: equal-length longitude/latitude lists. *style*: GMT symbol
    ("c0.3c" circle 0.3cm, "a0.5c" star, "t0.4c" triangle, "s0.3c" square).
    *color*: fill color ("red", "blue", "0/0/255"). *pen*: outline pen.
    Returns an inline image or a file path.
    """
    import pygmt

    if len(lons) != len(lats):
        return f"ERROR: lons ({len(lons)}) and lats ({len(lats)}) must be equal length."
    fig = pygmt.Figure()
    fig.basemap(region=region, projection=projection, frame=frame)
    if coast:
        fig.coast(shorelines="1/0.25p,gray")
    if lons:
        fig.plot(x=lons, y=lats, style=style, fill=color, pen=pen)
    return _finish(fig, output_path, dpi, f"{len(lons)} points on map")


# ---------------------------------------------------------------------------
# Tool 4: plot_xy — generic x-y line/scatter plot (no map projection)
# ---------------------------------------------------------------------------
@mcp.tool()
def plot_xy(
    x: list[float],
    y: list[float],
    *,
    title: str = "",
    x_label: str = "x",
    y_label: str = "y",
    style: str = "c0.2c",
    color: str = "black",
    pen: str = "0.5p,black",
    region: list[float] | None = None,
    output_path: str | None = None,
    dpi: int = 150,
) -> str:
    """Make a Cartesian x-y scatter/line plot (NOT a map; no projection).

    *x*/*y*: equal-length value lists. *style*: "c0.2c" scatter, "l0.5p" line,
    "s0.3c" squares. If *region* is None it's auto-scaled to the data.
    Returns an inline image or a file path.
    """
    import pygmt

    if len(x) != len(y):
        return f"ERROR: x ({len(x)}) and y ({len(y)}) must be equal length."
    fig = pygmt.Figure()
    if region is None:
        # Auto-region with a small padding around the data.
        pad_x = (max(x) - min(x)) * 0.05 or 1
        pad_y = (max(y) - min(y)) * 0.05 or 1
        region = [min(x) - pad_x, max(x) + pad_x, min(y) - pad_y, max(y) + pad_y]
    fig.basemap(region=region, projection="X12c/8c",
                frame=[f"a", f'+t"{title}"', f'x+l"{x_label}"', f'y+l"{y_label}"'])
    fig.plot(x=x, y=y, style=style, fill=color, pen=pen)
    return _finish(fig, output_path, dpi, f"xy plot {len(x)} pts")


def frame_str(xlabel: str, ylabel: str, title: str) -> list[str]:
    """Build a GMT frame spec list with labeled axes (kept for compatibility)."""
    return [f"a", f'+t"{title}"', f'x+l"{xlabel}"', f'y+l"{ylabel}"']


# ---------------------------------------------------------------------------
# Tool 5: coast_map — just a coastline/bathymetry map (no data)
# ---------------------------------------------------------------------------
@mcp.tool()
def coast_map(
    region: list[float],
    projection: str = "M15c",
    *,
    land: str = "tan",
    water: str = "lightblue",
    shorelines: str = "1/0.5p,black",
    frame: str = "af",
    resolution: str = "i",
    output_path: str | None = None,
    dpi: int = 150,
) -> str:
    """Draw a coastline/bathymetry map (no data overlaid).

    *resolution*: coastline detail ("c" crude, "l" low, "i" intermediate [default],
    "h" high, "f" full). Higher = slower but finer. Useful as a base for later
    overlays. Returns an inline image or a file path.
    """
    import pygmt

    fig = pygmt.Figure()
    fig.coast(region=region, projection=projection, frame=frame,
              land=land, water=water, shorelines=shorelines, resolution=resolution)
    return _finish(fig, output_path, dpi, f"coast map {region} {resolution}")


# ---------------------------------------------------------------------------
# Tool 6: text_on_map — add labels to a map
# ---------------------------------------------------------------------------
@mcp.tool()
def text_on_map(
    region: list[float],
    projection: str,
    lons: list[float],
    lats: list[float],
    texts: list[str],
    *,
    font: str = "12p,Helvetica,black",
    coast: bool = True,
    frame: str = "af",
    output_path: str | None = None,
    dpi: int = 150,
) -> str:
    """Place text labels (e.g. station codes, city names) on a map.

    *lons*/*lats*/*texts*: three equal-length lists giving label positions and
    strings. *font*: GMT font spec "size,family,color" (e.g. "14p,Helvetica-Bold,red").
    Returns an inline image or a file path.
    """
    import pygmt

    n = len(lons)
    if not (len(lats) == n and len(texts) == n):
        return "ERROR: lons, lats, texts must be equal length."
    fig = pygmt.Figure()
    fig.basemap(region=region, projection=projection, frame=frame)
    if coast:
        fig.coast(shorelines="1/0.25p,gray")
    if n:
        fig.text(x=lons, y=lats, text=texts, font=font)
    return _finish(fig, output_path, dpi, f"{n} labels on map")


# ---------------------------------------------------------------------------
# finish helper — render, inline-or-file decision
# ---------------------------------------------------------------------------
def _finish(fig, output_path, dpi, summary) -> str:
    """Render *fig* to PNG; return inline Image if small, else file path."""
    try:
        png = render_fig_to_png(fig, dpi=dpi)
    except Exception as exc:
        return f"ERROR rendering figure: {exc}"
    if output_path is None:
        try:
            img = figure_to_image(png)
            # Returning an Image object from a tool whose annotation is str:
            # FastMCP handles Image instances as content; the annotation is
            # only for schema, which doesn't apply to image return types.
            return img  # type: ignore[return-value]
        except ValueError:
            # Too big for inline; write to a temp file.
            import tempfile
            fd, output_path = tempfile.mkstemp(prefix="gmt_mcp_", suffix=".png")
            os.close(fd)
    path = save_figure(png, output_path)
    return f"{summary} → {path} ({len(png)} bytes)"


def main() -> None:
    """Console entry point — launches the server over stdio."""
    mcp.run()


if __name__ == "__main__":
    main()
