"""obs-raw-mcp — IGGCAS OBS raw → SAC/SU conversion as an MCP server.

Mount only this server when you want to convert OBS proprietary raw format
to standard SAC (continuous) or SU (shot gathers):

    claude mcp add obs-raw -- uvx obs-raw-mcp

Requires IGGCAS raw2su and graw2sac on PATH (Wang Yuan, IGGCAS).
The server detects both via ``shutil.which``.
"""

__version__ = "0.1.0"
