"""
WwiseMCP Server
FastMCP instance + 19 tools + lifecycle management

Start:
  python -m wwise_mcp.server          # stdio mode (Cursor / Claude Desktop)
  python -m wwise_mcp.server --sse    # SSE mode
"""

import asyncio
import logging
import os
import sys
from contextlib import asynccontextmanager
from typing import Any

from fastmcp import FastMCP

from .config import settings
from .core import init_connection
from .prompts.system_prompt import STATIC_SYSTEM_PROMPT
from .rag.context_collector import build_dynamic_context
from .tools import (
    # Query
    get_project_hierarchy,
    get_object_properties,
    search_objects,
    get_bus_topology,
    get_event_actions,
    get_soundbank_info,
    get_rtpc_list,
    get_selected_objects,
    # Action
    create_object,
    set_property,
    create_event,
    assign_bus,
    delete_object,
    move_object,
    preview_event,
    # Verify
    verify_structure,
    verify_event_completeness,
    # Fallback
    execute_waapi,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("wwise_mcp.server")


# ------------------------------------------------------------------
# FastMCP
# ------------------------------------------------------------------

mcp = FastMCP(
    name="WwiseMCP",
    instructions=STATIC_SYSTEM_PROMPT,
)


# ------------------------------------------------------------------
# Lifecycle
# ------------------------------------------------------------------

_connection_initialized = False

async def _ensure_connection():
    global _connection_initialized
    if not _connection_initialized:
        conn = init_connection()
        try:
            await conn.ensure_connected()
            logger.info("WAAPI connected: %s", settings.waapi_url)
        except Exception as e:
            logger.warning("WAAPI initial connection failed (will retry on tool call): %s", e)
        _connection_initialized = True


# ------------------------------------------------------------------
# Query tools (8)
# ------------------------------------------------------------------

@mcp.tool()
async def tool_get_project_hierarchy() -> dict:
    """
    Get a top-level overview of the Wwise project structure.
    Returns object counts and types for each major hierarchy
    (Actor-Mixer, Master-Mixer, Events, etc.).
    Note: In Wwise 2024.1 Auto-Defined SoundBank mode the SoundBanks node
    may be empty — this is expected behaviour.
    """
    await _ensure_connection()
    return await get_project_hierarchy()


@mcp.tool()
async def tool_get_selected_objects() -> dict:
    """
    Get the list of objects currently selected in the Wwise UI.

    Allows Claude to know what the user has selected without requiring
    them to copy-paste paths. Call this first before any operation so
    the selected objects can serve as the starting point.
    """
    await _ensure_connection()
    return await get_selected_objects()


@mcp.tool()
async def tool_get_object_properties(
    object_path: str,
    page: int = 1,
    page_size: int = 30,
) -> dict:
    """
    Get property details for a specific Wwise object.

    Args:
        object_path: WAAPI path, e.g. '\\\\Actor-Mixer Hierarchy\\\\Default Work Unit\\\\MySFX'
        page:        Page number (starts at 1)
        page_size:   Properties per page, default 30
    """
    await _ensure_connection()
    return await get_object_properties(object_path, page, page_size)


@mcp.tool()
async def tool_search_objects(
    query: str,
    type_filter: str | None = None,
    max_results: int = 20,
) -> dict:
    """
    Fuzzy-search Wwise objects by name.

    Args:
        query:       Search keyword (case-insensitive substring match)
        type_filter: Optional type filter, e.g. 'Sound SFX', 'Event', 'Bus', 'GameParameter'
        max_results: Maximum results to return, default 20
    """
    await _ensure_connection()
    return await search_objects(query, type_filter, max_results)


@mcp.tool()
async def tool_get_bus_topology() -> dict:
    """
    Get the full Bus topology from the Master-Mixer Hierarchy (mixing routing architecture).
    """
    await _ensure_connection()
    return await get_bus_topology()


@mcp.tool()
async def tool_get_event_actions(event_path: str) -> dict:
    """
    Get all Actions under a specific Event (type, Target reference, etc.).

    Args:
        event_path: Full WAAPI path of the Event object
    """
    await _ensure_connection()
    return await get_event_actions(event_path)


@mcp.tool()
async def tool_get_soundbank_info(soundbank_name: str | None = None) -> dict:
    """
    Get SoundBank information.

    Args:
        soundbank_name: Specific bank name; None returns an overview of all banks.

    Note: Wwise 2024.1 uses Auto-Defined SoundBank by default — manual management
    is usually unnecessary.
    """
    await _ensure_connection()
    return await get_soundbank_info(soundbank_name)


@mcp.tool()
async def tool_get_rtpc_list(max_results: int = 50) -> dict:
    """
    Get all Game Parameters (RTPCs) in the project, with name, range, and default value.

    Args:
        max_results: Maximum number to return, default 50
    """
    await _ensure_connection()
    return await get_rtpc_list(max_results)


# ------------------------------------------------------------------
# Action tools (7)
# ------------------------------------------------------------------

@mcp.tool()
async def tool_create_object(
    name: str,
    obj_type: str,
    parent_path: str,
    on_conflict: str = "rename",
    notes: str = "",
) -> dict:
    """
    Create a Wwise object under the specified parent node.

    Args:
        name:        New object name
        obj_type:    Type: 'Sound SFX' | 'Event' | 'Bus' | 'BlendContainer' | 'Action' etc.
        parent_path: Full WAAPI path of the parent object
        on_conflict: Conflict handling: 'rename' (default) | 'replace' | 'fail'
        notes:       Optional notes
    """
    await _ensure_connection()
    return await create_object(name, obj_type, parent_path, on_conflict, notes)


@mcp.tool()
async def tool_set_property(
    object_path: str,
    property: str | None = None,
    value: Any = None,
    properties: dict | None = None,
    platform: str | None = None,
) -> dict:
    """
    Set one or more properties on an object.

    Args:
        object_path: Target object path
        property:    Single property name, e.g. 'Volume', 'Pitch', 'LowPassFilter'
        value:       Single property value (use with property)
        properties:  Batch property dict, e.g. {"Volume": -6.0, "Pitch": 200} (recommended)
        platform:    Target platform (None = all platforms)
    """
    await _ensure_connection()
    return await set_property(object_path, property, value, properties, platform)


@mcp.tool()
async def tool_preview_event(event_path: str, action: str = "play") -> dict:
    """
    Preview an Event in Wwise Authoring via the Transport API (no game connection needed).

    Args:
        event_path: Full WAAPI path of the Event
        action:     'play' (default) | 'stop' | 'pause' | 'resume'

    Equivalent to pressing F5 in Wwise. Use this to verify audio changes immediately
    after editing parameters — no SoundBank rebuild required.
    """
    await _ensure_connection()
    return await preview_event(event_path, action)


@mcp.tool()
async def tool_create_event(
    event_name: str,
    action_type: str,
    target_path: str,
    parent_path: str = "\\Events\\Default Work Unit",
) -> dict:
    """
    Create a Wwise Event and its Action in one step (Event -> Action -> Target).

    Args:
        event_name:  Event name, recommended verb prefix e.g. 'Play_Explosion'
        action_type: 'Play' | 'Stop' | 'Pause' | 'Resume' | 'Break' | 'Mute' | 'UnMute'
        target_path: Action target object path (Sound / Container etc.)
        parent_path: Event parent path, default is Default Work Unit

    Wwise 2024.1: No SoundBank rebuild needed — verify immediately via Live Editing.
    """
    await _ensure_connection()
    return await create_event(event_name, action_type, target_path, parent_path)


@mcp.tool()
async def tool_assign_bus(object_path: str, bus_path: str) -> dict:
    """
    Route an object to a specific Bus (set OutputBus).

    Args:
        object_path: Target Sound/Container path
        bus_path:    Full Bus path, e.g. '\\\\Master-Mixer Hierarchy\\\\Master Audio Bus\\\\SFX'
    """
    await _ensure_connection()
    return await assign_bus(object_path, bus_path)


@mcp.tool()
async def tool_delete_object(object_path: str, force: bool = False) -> dict:
    """
    Delete a Wwise object.

    Args:
        object_path: Full path of the object to delete
        force:       False (default) checks references first; True skips the check

    Tip: run verify_structure before deleting to avoid dangling references.
    """
    await _ensure_connection()
    return await delete_object(object_path, force)


@mcp.tool()
async def tool_move_object(object_path: str, new_parent_path: str) -> dict:
    """
    Move an object to a new parent node (for reorganising project structure).

    Args:
        object_path:     Full path of the object to move
        new_parent_path: Target parent node path
    """
    await _ensure_connection()
    return await move_object(object_path, new_parent_path)


# ------------------------------------------------------------------
# Verify tools (2)
# ------------------------------------------------------------------

@mcp.tool()
async def tool_verify_structure(scope_path: str | None = None) -> dict:
    """
    Structural integrity check. Call this after completing each independent goal.

    Checks: Event->Action links, Action->Target references, Bus routing,
    property value ranges, orphaned objects.

    Args:
        scope_path: Path to limit the check scope (None = full project)
    """
    await _ensure_connection()
    return await verify_structure(scope_path)


@mcp.tool()
async def tool_verify_event_completeness(event_path: str) -> dict:
    """
    Verify that an Event can fire correctly in Wwise 2024.1 Auto-Defined SoundBank mode.

    Checks: Event exists -> Actions complete -> Targets valid ->
    AudioFileSource has audio file -> Auto-Defined Bank ready.

    Args:
        event_path: Full path of the Event to verify
    """
    await _ensure_connection()
    return await verify_event_completeness(event_path)


# ------------------------------------------------------------------
# Fallback tool (1)
# ------------------------------------------------------------------

@mcp.tool()
async def tool_execute_waapi(
    uri: str,
    args: dict = {},
    opts: dict = {},
) -> dict:
    """
    Execute a raw WAAPI call directly (fallback tool for cases not covered by other tools).

    Args:
        uri:  WAAPI function URI, e.g. 'ak.wwise.core.object.get'
        args: WAAPI arguments dict
        opts: WAAPI options dict

    Security: the following URIs are blacklisted:
    project.open / project.close / project.save / remote.connect / remote.disconnect
    """
    await _ensure_connection()
    return await execute_waapi(uri, args, opts)


# ------------------------------------------------------------------
# System Prompt resource
# ------------------------------------------------------------------

@mcp.resource("wwise://system_prompt")
async def get_system_prompt() -> str:
    """Wwise 2024.1 domain system prompt (for MCP clients to inject into LLM context)"""
    await _ensure_connection()
    dynamic = await build_dynamic_context()
    return STATIC_SYSTEM_PROMPT + dynamic


# ------------------------------------------------------------------
# Entry point
# ------------------------------------------------------------------

def main():
    import argparse
    parser = argparse.ArgumentParser(description="WwiseMCP Server - Wwise 2024.1 AI Agent")
    parser.add_argument("--host", default=settings.host)
    parser.add_argument("--port", type=int, default=settings.port)
    parser.add_argument("--transport", choices=["stdio", "sse"], default="stdio")
    parser.add_argument("--sse-port", type=int, default=8765)
    args = parser.parse_args()

    settings.host = args.host
    settings.port = args.port

    logger.info("WwiseMCP starting, WAAPI target: %s, transport: %s",
                settings.waapi_url, args.transport)

    if args.transport == "sse":
        mcp.run(transport="sse", host="127.0.0.1", port=args.sse_port)
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
