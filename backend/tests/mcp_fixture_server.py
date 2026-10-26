"""Real MCP protocol fixture; not an application acceptance substitute."""
import os
from pathlib import Path
from mcp.server.fastmcp import FastMCP

server = FastMCP('axx-test-external', log_level='CRITICAL')


@server.tool()
def add_numbers(left: int, right: int) -> dict:
    """Add two integers in the external process."""
    return {'sum': left + right}


@server.tool()
def append_marker(text: str) -> dict:
    """Append a test marker; acknowledgement does not verify an application effect."""
    with Path(os.environ['AXX_TEST_MCP_FILE']).open('a', encoding='utf-8') as stream:
        stream.write(text + '\n')
    return {'accepted': True}


if __name__ == '__main__': server.run(transport='stdio')
