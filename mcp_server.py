"""MCP (Model Context Protocol) server integration for DigitalOcean DNS Manager.

Implements MCP-over-SSE protocol directly in Flask, exposing DNS management
tools that call the same internal functions as the REST API routes.
"""

import json
import uuid
import queue
import hmac
import threading
from flask import Response, request, jsonify, render_template_string


# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

MCP_TOOLS = [
    {
        "name": "health_check",
        "description": "Return the health status of the DigitalOcean DNS Manager and the configured DNS zone.",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "list_records",
        "description": (
            "List all DNS records in the configured DigitalOcean DNS zone. "
            "Returns an array of records with name, type, TTL, FQDN, ID, and values."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "create_record",
        "description": (
            "Create a new DNS record in the configured zone. "
            "Supports A, AAAA, CNAME, MX, TXT, SRV, and NS record types. "
            "MX values use 'priority exchange' format. "
            "SRV values use 'priority weight port target' format."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Record name (use @ for root domain)",
                },
                "type": {
                    "type": "string",
                    "enum": ["A", "AAAA", "CNAME", "MX", "TXT", "SRV", "NS"],
                    "description": "DNS record type",
                },
                "values": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Record values. MX: 'priority exchange', "
                        "SRV: 'priority weight port target'"
                    ),
                },
                "ttl": {
                    "type": "integer",
                    "description": "Time to live in seconds (default 3600)",
                    "default": 3600,
                },
            },
            "required": ["name", "type", "values"],
        },
    },
    {
        "name": "update_record",
        "description": (
            "Update an existing DNS record by type and name. "
            "Optionally provide the record ID; if omitted the record is looked up automatically."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "record_type": {
                    "type": "string",
                    "enum": ["A", "AAAA", "CNAME", "MX", "TXT", "SRV", "NS"],
                    "description": "DNS record type",
                },
                "record_name": {
                    "type": "string",
                    "description": "Current record name",
                },
                "values": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Updated record values",
                },
                "ttl": {
                    "type": "integer",
                    "description": "Time to live in seconds (default 3600)",
                    "default": 3600,
                },
                "new_name": {
                    "type": "string",
                    "description": "New record name (if renaming)",
                },
                "id": {
                    "type": "integer",
                    "description": "Record ID (optional, looked up if omitted)",
                },
            },
            "required": ["record_type", "record_name", "values"],
        },
    },
    {
        "name": "delete_record",
        "description": (
            "Delete a DNS record by type and name. "
            "Optionally provide the record ID; if omitted the record is looked up automatically."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "record_type": {
                    "type": "string",
                    "enum": ["A", "AAAA", "CNAME", "MX", "TXT", "SRV", "NS"],
                    "description": "DNS record type",
                },
                "record_name": {
                    "type": "string",
                    "description": "Record name to delete",
                },
                "id": {
                    "type": "integer",
                    "description": "Record ID (optional, looked up if omitted)",
                },
            },
            "required": ["record_type", "record_name"],
        },
    },
]


# ---------------------------------------------------------------------------
# Session management
# ---------------------------------------------------------------------------

class McpSession:
    """Holds per-connection state for an MCP SSE session."""

    def __init__(self):
        self.id = str(uuid.uuid4())
        self.message_queue: queue.Queue = queue.Queue()
        self.initialized = False


_sessions: dict[str, McpSession] = {}
_sessions_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Auth helper
# ---------------------------------------------------------------------------

def _validate_bearer_token(req, auth_dict):
    """Return True when the request carries a valid Bearer token."""
    auth_header = req.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return False
    token = auth_header[7:]
    return hmac.compare_digest(token, auth_dict["api_token"])


# ---------------------------------------------------------------------------
# Tool execution
# ---------------------------------------------------------------------------

def _format_records(raw_records, zone):
    """Convert raw DO API records into the standard response format."""
    formatted = []
    for record in raw_records:
        rec = {
            "name": record.get("name"),
            "type": record.get("type"),
            "ttl": record.get("ttl"),
            "id": record.get("id"),
            "fqdn": (
                f"{record.get('name')}.{zone}"
                if record.get("name") != "@"
                else zone
            ),
        }
        data_value = record.get("data")
        rtype = record.get("type")
        if rtype == "MX":
            rec["values"] = [f"{record.get('priority', 0)} {data_value}"]
        elif rtype == "SRV":
            rec["values"] = [
                f"{record.get('priority', 0)} {record.get('weight', 0)} "
                f"{record.get('port', 0)} {data_value}"
            ]
        else:
            rec["values"] = [data_value] if data_value else []
        formatted.append(rec)
    return formatted


def _prepare_record_data(record_type, values):
    """Parse values list into DO API record fields. Returns (fields_dict, error_string)."""
    fields: dict = {}

    if record_type in ("A", "AAAA", "TXT"):
        fields["data"] = values[0]
    elif record_type in ("CNAME", "NS"):
        if len(values) > 1 and record_type == "CNAME":
            return None, "CNAME records can only have one value"
        val = values[0]
        fields["data"] = val if val.endswith(".") else val + "."
    elif record_type == "MX":
        parts = values[0].split(" ", 1)
        if len(parts) != 2:
            return None, 'MX record must be in format: "priority exchange"'
        fields["priority"] = int(parts[0])
        exchange = parts[1]
        fields["data"] = exchange if exchange.endswith(".") else exchange + "."
    elif record_type == "SRV":
        parts = values[0].split(" ", 3)
        if len(parts) != 4:
            return None, 'SRV record must be in format: "priority weight port target"'
        fields["priority"] = int(parts[0])
        fields["weight"] = int(parts[1])
        fields["port"] = int(parts[2])
        target = parts[3]
        fields["data"] = target if target.endswith(".") else target + "."
    else:
        return None, f"Unsupported record type: {record_type}"

    return fields, None


def call_tool(name, arguments):
    """Execute an MCP tool and return a plain dict result."""
    from app import fetch_all_domain_records, make_do_request, config, is_config_complete

    # ------------------------------------------------------------------
    if name == "health_check":
        return {"status": "healthy", "zone": config.get("DNS_ZONE")}

    # ------------------------------------------------------------------
    if name == "list_records":
        if not is_config_complete():
            return {"error": "DigitalOcean configuration is incomplete"}
        records, err = fetch_all_domain_records()
        if err is not None:
            error_msg = err.json().get("message", "Unknown error")
            return {"error": f"Failed to fetch records: {error_msg}"}
        return {
            "records": _format_records(records, config["DNS_ZONE"]),
            "zone": config["DNS_ZONE"],
        }

    # ------------------------------------------------------------------
    if name == "create_record":
        record_name = arguments.get("name")
        record_type = arguments.get("type")
        ttl = arguments.get("ttl", 3600)
        values = arguments.get("values", [])

        if not record_name or not record_type or not values:
            return {"error": "Missing required fields: name, type, values"}
        if not is_config_complete():
            return {"error": "DigitalOcean configuration is incomplete"}

        record_data = {"type": record_type, "name": record_name, "ttl": ttl}
        extra, err = _prepare_record_data(record_type, values)
        if err:
            return {"error": err}
        record_data.update(extra)

        response = make_do_request(
            "POST", f"/domains/{config['DNS_ZONE']}/records", record_data
        )
        if response.status_code in (200, 201):
            return {"message": "Record created successfully", "name": record_name}
        error_msg = response.json().get("message", "Unknown error")
        return {"error": f"Failed to create record: {error_msg}"}

    # ------------------------------------------------------------------
    if name == "update_record":
        record_type = arguments.get("record_type")
        record_name = arguments.get("record_name")
        values = arguments.get("values", [])
        ttl = arguments.get("ttl", 3600)
        new_name = arguments.get("new_name", record_name)
        record_id = arguments.get("id")

        if not values:
            return {"error": "Missing required field: values"}
        if not is_config_complete():
            return {"error": "DigitalOcean configuration is incomplete"}

        if not record_id:
            all_records, err = fetch_all_domain_records()
            if all_records is not None:
                for rec in all_records:
                    if rec.get("name") == record_name and rec.get("type") == record_type:
                        record_id = rec.get("id")
                        break
            if not record_id:
                return {"error": f"Record {record_name} ({record_type}) not found"}

        update_data = {"type": record_type, "name": new_name, "ttl": ttl}
        extra, err = _prepare_record_data(record_type, values)
        if err:
            return {"error": err}
        update_data.update(extra)

        response = make_do_request(
            "PUT", f"/domains/{config['DNS_ZONE']}/records/{record_id}", update_data
        )
        if response.status_code == 200:
            return {"message": "Record updated successfully", "name": new_name}
        error_msg = response.json().get("message", "Unknown error")
        return {"error": f"Failed to update record: {error_msg}"}

    # ------------------------------------------------------------------
    if name == "delete_record":
        record_type = arguments.get("record_type")
        record_name = arguments.get("record_name")
        record_id = arguments.get("id")

        if not is_config_complete():
            return {"error": "DigitalOcean configuration is incomplete"}

        if not record_id:
            all_records, err = fetch_all_domain_records()
            if all_records is not None:
                for rec in all_records:
                    if rec.get("name") == record_name and rec.get("type") == record_type:
                        record_id = rec.get("id")
                        break
            if not record_id:
                return {"error": f"Record {record_name} ({record_type}) not found"}

        response = make_do_request(
            "DELETE", f"/domains/{config['DNS_ZONE']}/records/{record_id}"
        )
        if response.status_code == 204:
            return {"message": "Record deleted successfully", "name": record_name}
        error_msg = (
            response.json().get("message", "Unknown error") if response.text else "Unknown error"
        )
        return {"error": f"Failed to delete record: {error_msg}"}

    # ------------------------------------------------------------------
    return {"error": f"Unknown tool: {name}"}


# ---------------------------------------------------------------------------
# MCP JSON-RPC message handling
# ---------------------------------------------------------------------------

def handle_mcp_message(session, message):
    """Process an MCP JSON-RPC message and return a response dict (or None for notifications)."""
    method = message.get("method")
    msg_id = message.get("id")

    if method == "initialize":
        session.initialized = True
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "dodns-mcp", "version": "1.0.0"},
            },
        }

    if method == "notifications/initialized":
        return None  # no response for notifications

    if method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {"tools": MCP_TOOLS},
        }

    if method == "tools/call":
        tool_name = message.get("params", {}).get("name")
        arguments = message.get("params", {}).get("arguments", {})
        try:
            result = call_tool(tool_name, arguments)
            is_error = "error" in result and len(result) == 1
        except Exception as exc:
            result = {"error": str(exc)}
            is_error = True

        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "content": [{"type": "text", "text": json.dumps(result, indent=2)}],
                "isError": is_error,
            },
        }

    if method == "ping":
        return {"jsonrpc": "2.0", "id": msg_id, "result": {}}

    # Unknown method
    return {
        "jsonrpc": "2.0",
        "id": msg_id,
        "error": {"code": -32601, "message": f"Method not found: {method}"},
    }


# ---------------------------------------------------------------------------
# /mcpdocs HTML page
# ---------------------------------------------------------------------------

_MCPDOCS_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>MCP Tools - DigitalOcean DNS Manager</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
*,*::before,*::after{margin:0;padding:0;box-sizing:border-box}

:root{
  --font-sans:'DM Sans',-apple-system,BlinkMacSystemFont,sans-serif;
  --font-mono:'JetBrains Mono','SF Mono',Consolas,monospace;
  --bg-body:#f4f5f7;--bg-surface:#ffffff;--bg-input:#ffffff;
  --text-primary:#111318;--text-secondary:#5f6672;--text-tertiary:#8b919d;
  --border:#e3e5e9;--accent:#3b6ee8;--accent-subtle:#eef2fc;--accent-text:#2952a3;
  --radius-sm:6px;--radius-md:8px;--radius-lg:10px;
  --shadow-sm:0 1px 2px rgba(0,0,0,.04),0 1px 4px rgba(0,0,0,.02);
  --shadow-md:0 2px 8px rgba(0,0,0,.06),0 1px 2px rgba(0,0,0,.04);
  --tag-bg:#e8eef8;--tag-text:#2952a3;
}

@media(prefers-color-scheme:dark){
  :root{
    --bg-body:#0f1117;--bg-surface:#1a1d24;--bg-input:#24272f;
    --text-primary:#e8eaed;--text-secondary:#9ba0ab;--text-tertiary:#6b717d;
    --border:#2e323a;--accent:#5b8def;--accent-subtle:#1c2638;--accent-text:#8bb4f7;
    --shadow-sm:0 1px 2px rgba(0,0,0,.2);--shadow-md:0 2px 8px rgba(0,0,0,.3);
    --tag-bg:#1c2638;--tag-text:#8bb4f7;
  }
}

body{font-family:var(--font-sans);background:var(--bg-body);color:var(--text-primary);line-height:1.6;padding:2rem 1rem}
.container{max-width:860px;margin:0 auto}
h1{font-size:1.6rem;font-weight:600;margin-bottom:.25rem}
.subtitle{color:var(--text-secondary);margin-bottom:2rem;font-size:.95rem}
.subtitle a{color:var(--accent);text-decoration:none}
.subtitle a:hover{text-decoration:underline}

.tool-card{
  background:var(--bg-surface);border:1px solid var(--border);border-radius:var(--radius-lg);
  padding:1.5rem;margin-bottom:1.25rem;box-shadow:var(--shadow-sm);
}
.tool-card:hover{box-shadow:var(--shadow-md)}
.tool-name{font-family:var(--font-mono);font-weight:600;font-size:1.05rem;color:var(--accent)}
.tool-desc{color:var(--text-secondary);margin:.5rem 0 1rem;font-size:.92rem}

.params-heading{font-size:.82rem;font-weight:600;text-transform:uppercase;letter-spacing:.04em;color:var(--text-tertiary);margin-bottom:.5rem}
.param{display:flex;gap:.75rem;padding:.45rem 0;border-bottom:1px solid var(--border);align-items:baseline;flex-wrap:wrap}
.param:last-child{border-bottom:none}
.param-name{font-family:var(--font-mono);font-weight:500;font-size:.88rem;min-width:120px;color:var(--text-primary)}
.param-meta{display:flex;gap:.4rem;flex-wrap:wrap;align-items:center}
.tag{display:inline-block;font-size:.72rem;font-weight:500;padding:1px 7px;border-radius:4px;background:var(--tag-bg);color:var(--tag-text)}
.tag.required{background:#fef1f1;color:#a3232b}
@media(prefers-color-scheme:dark){.tag.required{background:#2a1517;color:#f09095}}
.param-desc{font-size:.85rem;color:var(--text-secondary);width:100%;padding-left:0}
.param-enum{font-family:var(--font-mono);font-size:.78rem;color:var(--text-tertiary);margin-top:.15rem}

.no-params{color:var(--text-tertiary);font-size:.88rem;font-style:italic}
.badge-sse{display:inline-block;font-size:.72rem;font-weight:600;padding:2px 8px;border-radius:4px;background:var(--accent-subtle);color:var(--accent-text);margin-left:.5rem;vertical-align:middle}

.endpoint-box{
  background:var(--bg-surface);border:1px solid var(--border);border-radius:var(--radius-md);
  padding:1rem 1.25rem;margin-bottom:1.5rem;font-family:var(--font-mono);font-size:.85rem;
  color:var(--text-secondary);box-shadow:var(--shadow-sm);
}
.endpoint-box strong{color:var(--text-primary);font-weight:600}
</style>
</head>
<body>
<div class="container">
  <h1>MCP Tools <span class="badge-sse">SSE</span></h1>
  <p class="subtitle">Model Context Protocol tools for DigitalOcean DNS Manager &middot; <a href="/">Back to app</a></p>

  <div class="endpoint-box">
    <strong>SSE endpoint:</strong> GET /mcp/sse<br>
    <strong>Messages:</strong> POST /mcp/messages?session_id=&lt;id&gt;<br>
    <strong>Auth:</strong> Bearer token (same as REST API)
  </div>

  {% for tool in tools %}
  <div class="tool-card">
    <div class="tool-name">{{ tool.name }}</div>
    <div class="tool-desc">{{ tool.description }}</div>

    {% set props = tool.inputSchema.get('properties', {}) %}
    {% set req = tool.inputSchema.get('required', []) %}

    {% if props %}
      <div class="params-heading">Parameters</div>
      {% for pname, pschema in props.items() %}
      <div class="param">
        <span class="param-name">{{ pname }}</span>
        <span class="param-meta">
          <span class="tag">{{ pschema.get('type', 'any') }}</span>
          {% if pname in req %}<span class="tag required">required</span>{% endif %}
          {% if pschema.get('default') is not none and pschema.get('default')|string != '' %}
            <span class="tag">default: {{ pschema.get('default') }}</span>
          {% endif %}
        </span>
        {% if pschema.get('description') %}
        <span class="param-desc">{{ pschema.description }}</span>
        {% endif %}
        {% if pschema.get('enum') %}
        <span class="param-enum">{{ pschema.enum | join(', ') }}</span>
        {% endif %}
      </div>
      {% endfor %}
    {% else %}
      <div class="no-params">No parameters</div>
    {% endif %}
  </div>
  {% endfor %}
</div>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Flask route registration
# ---------------------------------------------------------------------------

def register_mcp_routes(app, auth_dict):
    """Register MCP SSE transport routes and /mcpdocs on the Flask app."""

    @app.route("/mcp/sse", methods=["GET"])
    def mcp_sse():
        if not _validate_bearer_token(request, auth_dict):
            return jsonify({"error": "Authentication required"}), 401

        session = McpSession()
        with _sessions_lock:
            _sessions[session.id] = session

        def generate():
            try:
                # Tell the client where to POST messages
                yield f"event: endpoint\ndata: /mcp/messages?session_id={session.id}\n\n"

                while True:
                    try:
                        msg = session.message_queue.get(timeout=30)
                        if msg is None:  # shutdown signal
                            break
                        yield f"event: message\ndata: {json.dumps(msg)}\n\n"
                    except queue.Empty:
                        yield ": keepalive\n\n"
            finally:
                with _sessions_lock:
                    _sessions.pop(session.id, None)

        resp = Response(generate(), mimetype="text/event-stream")
        resp.headers["Cache-Control"] = "no-cache"
        resp.headers["X-Accel-Buffering"] = "no"
        resp.headers["Connection"] = "keep-alive"
        return resp

    @app.route("/mcp/messages", methods=["POST"])
    def mcp_messages():
        if not _validate_bearer_token(request, auth_dict):
            return jsonify({"error": "Authentication required"}), 401

        session_id = request.args.get("session_id")
        with _sessions_lock:
            session = _sessions.get(session_id)
        if not session:
            return jsonify({"error": "Invalid or expired session"}), 404

        message = request.get_json(silent=True)
        if not message:
            return jsonify({"error": "Invalid JSON body"}), 400

        response = handle_mcp_message(session, message)

        if response is not None:
            session.message_queue.put(response)

        return "", 202

    @app.route("/mcpdocs")
    def mcpdocs():
        return render_template_string(_MCPDOCS_TEMPLATE, tools=MCP_TOOLS)
