"""cwp-su-mcp — CWP/SU (Seismic Un*x) tools as an MCP server.

Mount only this server when you want Seismic Unix trace-processing
capabilities (filter, gain, window, sort, header ops):

    claude mcp add su -- uvx cwp-su-mcp

Requires a working CWP-SU installation with CWPROOT set and its bin on PATH.
"""

__version__ = "0.1.0"
