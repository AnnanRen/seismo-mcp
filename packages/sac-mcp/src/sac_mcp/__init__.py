"""sac-mcp — SAC (Seismic Analysis Code) tools as an MCP server.

Mount only this server when you want SAC read/filter/preprocess/cut
capabilities:

    claude mcp add sac -- uvx sac-mcp

Requires a working SAC installation. The server detects it via SACHOME, then
``~/src/sac``, then ``/usr/local/sac``.
"""

__version__ = "0.1.0"
