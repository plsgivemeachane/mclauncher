"""MCP server exposing launcher control to AI assistants.

Run ``mclauncher-mcp`` (stdio, for Claude Code / Claude Desktop) or
``mclauncher-mcp --transport streamable-http --port 8765`` for an HTTP endpoint.
Requires the optional ``mcp`` extra: ``pip install 'mclauncher[mcp]'``.
"""

from __future__ import annotations

import argparse
import functools
from typing import Any, Callable

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from . import __version__
from .control import ControlError, LauncherController

INSTRUCTIONS = """\
Controls the local Minecraft offline-session launcher (same data as the desktop app).
Instances are referenced by id or exact name. install_instance and import_modpack return a
job immediately; poll get_job until status is 'succeeded' or 'failed' (installs can take minutes).
launch_game installs a not-yet-ready vanilla instance first and returns that job instead.
"""


def _tool(server: MCPServer, **options) -> Callable:
    """Register a tool whose failures reach the model with their real message.

    MCP 2.x hides unexpected exception text from clients; this server only runs
    locally for its owner, so launcher, file, and network errors are surfaced.
    """

    def decorate(function: Callable) -> Callable:
        @functools.wraps(function)
        def wrapper(*args, **kwargs):
            try:
                return function(*args, **kwargs)
            except (ControlError, OSError, RuntimeError, ValueError) as error:
                raise ToolError(str(error) or type(error).__name__) from error

        server.tool(**options)(wrapper)
        return function

    return decorate


def build_server(controller: LauncherController | None = None) -> MCPServer:
    control = controller or LauncherController()
    server = MCPServer(name="mclauncher", instructions=INSTRUCTIONS, version=__version__)
    tool = functools.partial(_tool, server)

    @tool()
    def launcher_status() -> dict[str, Any]:
        """Show data folder, username, memory setting, running game, and active jobs."""
        return control.status()

    @tool()
    def list_instances() -> list[dict[str, Any]]:
        """List every instance with its version, loader, and readiness."""
        return control.list_instances()

    @tool()
    def get_instance(instance: str) -> dict[str, Any]:
        """Show one instance (by id or name), including its folder and mods."""
        return control.get_instance(instance)

    @tool()
    def list_minecraft_versions(include_snapshots: bool = False, limit: int = 25) -> list[dict[str, Any]]:
        """List installable Minecraft versions, newest first (needs internet)."""
        return control.list_versions(include_snapshots=include_snapshots, limit=limit)

    @tool()
    def create_instance(name: str, version: str | None = None, install: bool = False) -> dict[str, Any]:
        """Create a vanilla instance. Omit version for the latest release. install=true also starts downloading it."""
        created = control.create_instance(name, version)
        if install:
            created["job"] = control.install_instance(created["id"])
        return created

    @tool()
    def rename_instance(instance: str, new_name: str) -> dict[str, Any]:
        """Rename an instance."""
        return control.rename_instance(instance, new_name)

    @tool()
    def install_instance(instance: str) -> dict[str, Any]:
        """Download Minecraft files and Java runtime for a vanilla instance. Returns a job to poll."""
        return control.install_instance(instance)

    @tool()
    def import_modpack(archive_path: str, name: str | None = None) -> dict[str, Any]:
        """Create an instance from a local Modrinth .mrpack or CurseForge exported .zip. Returns a job to poll."""
        return control.import_modpack(archive_path, name)

    @tool()
    def get_job(job_id: str) -> dict[str, Any]:
        """Check progress of an install/import job."""
        return control.job(job_id)

    @tool()
    def list_jobs() -> list[dict[str, Any]]:
        """List install/import jobs started by this server."""
        return control.list_jobs()

    @tool()
    def set_username(username: str) -> dict[str, Any]:
        """Set the offline player name (3-16 letters, digits, underscores)."""
        return control.set_username(username)

    @tool()
    def set_memory(memory_gib: int) -> dict[str, Any]:
        """Set how many GiB of RAM the game gets."""
        return control.set_memory(memory_gib)

    @tool()
    def launch_game(instance: str, username: str | None = None, memory_gib: int | None = None) -> dict[str, Any]:
        """Start Minecraft for an instance. Installs first if a vanilla instance is not ready."""
        return control.launch(instance, username=username, memory_gib=memory_gib)

    @tool()
    def game_status() -> dict[str, Any]:
        """Report whether a game is running and the last exit code."""
        return control.game_status()

    @tool()
    def stop_game(force: bool = False) -> dict[str, Any]:
        """Ask the running game to quit (force=true kills it immediately; unsaved progress may be lost)."""
        return control.stop_game(force=force)

    @tool()
    def read_game_log(instance: str, lines: int = 80) -> dict[str, Any]:
        """Return the last lines of an instance's minecraft.log, useful after a crash."""
        return control.read_log(instance, lines=lines)

    return server


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mclauncher-mcp", description="MCP control server for mclauncher")
    parser.add_argument("--data-root", help="launcher data folder (defaults to the desktop app's)")
    parser.add_argument("--transport", choices=("stdio", "streamable-http"), default="stdio")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args(argv)
    server = build_server(LauncherController(args.data_root))
    if args.transport == "stdio":
        server.run("stdio")
    else:
        server.run("streamable-http", host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
