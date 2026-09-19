#!/usr/bin/env python3
"""Narrow the pinned MemPalace server to public knowledge retrieval."""
from copy import deepcopy
from threading import BoundedSemaphore

from jsonschema import Draft202012Validator

PUBLIC_TOOLS = frozenset({
    "mempalace_search", "mempalace_get_drawer", "mempalace_list_drawers",
    "mempalace_list_wings", "mempalace_list_rooms", "mempalace_get_taxonomy",
})
MAX_ACTIVE_REQUESTS = 4
MAX_REQUEST_BYTES = 16 * 1024


def error(request, code, message):
    return {"jsonrpc": "2.0", "id": request.get("id") if isinstance(request, dict) else None,
            "error": {"code": code, "message": message}}


def install(server):
    # Fail closed if an image upgrade changes the integration contract.
    if not server._READ_ONLY or not PUBLIC_TOOLS <= server.TOOLS.keys():
        raise RuntimeError("Public MCP requires read-only mode and all retrieval tools")
    tools = {name: deepcopy(server.TOOLS[name]) for name in sorted(PUBLIC_TOOLS)}
    for name, tool in tools.items():
        schema = tool["input_schema"]
        schema["additionalProperties"] = False
        for key, prop in schema.get("properties", {}).items():
            if prop.get("type") == "string":
                prop["maxLength"] = min(prop.get("maxLength", 2048), 2048)
            if key == "offset":
                prop["maximum"] = 100000
            if key == "limit":
                prop["maximum"] = 20 if name == "mempalace_search" else 100
        Draft202012Validator.check_schema(schema)
    validators = {name: Draft202012Validator(tool["input_schema"])
                  for name, tool in tools.items()}
    server.TOOLS = tools
    server._HTTP_MAX_REQUEST_BYTES = MAX_REQUEST_BYTES
    dispatch = server._http_dispatch
    slots = BoundedSemaphore(MAX_ACTIVE_REQUESTS)

    def public_dispatch(request):
        if not isinstance(request, dict) or request.get("jsonrpc") != "2.0":
            return error(request, -32600, "Expected one JSON-RPC 2.0 request; batches are disabled")
        method = request.get("method")
        if not isinstance(method, str):
            return error(request, -32600, "Invalid method")
        if method in {"notifications/initialized", "notifications/cancelled"}:
            return None
        if method not in {"initialize", "ping", "tools/list", "tools/call"}:
            return error(request, -32601, "Method is not available on this public server")
        if not isinstance(request.get("params", {}), dict):
            return error(request, -32602, "Params must be an object")
        if method == "tools/call":
            params = request.get("params", {})
            name = params.get("name")
            if not isinstance(name, str) or name not in PUBLIC_TOOLS:
                return error(request, -32003, "This public read-only server permits only knowledge retrieval")
            if not validators[name].is_valid(params.get("arguments", {})):
                return error(request, -32602, "Arguments do not match the public tool schema")
        # Hold the slot until backend work actually finishes, even if the HTTP
        # client disconnects or the proxy times out. Never build an unbounded queue.
        if not slots.acquire(blocking=False):
            return error(request, -32000, "Server busy; retry with backoff")
        try:
            return dispatch(request)
        finally:
            slots.release()

    server._http_dispatch = public_dispatch


if __name__ == "__main__":
    import mempalace.mcp_server as server

    install(server)
    server.main()
