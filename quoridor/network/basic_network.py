from __future__ import annotations

DEFAULT_SERVER_HOST = "localhost"
DEFAULT_SERVER_PORT = 12345
DISCOVERY_PORT = 12346
_DISCOVERY_PREFIX = "QUORIDOR_SERVER"


def _validate_port(port: int) -> int:
    """Validate a TCP or UDP port."""
    if not 1 <= port <= 65535:
        raise ValueError(f"invalid port: {port}")
    return port


def parse_endpoint(
    raw: str | None,
    *,
    default_host: str = DEFAULT_SERVER_HOST,
    default_port: int = DEFAULT_SERVER_PORT,
) -> tuple[str, int]:
    """Parse a HOST[:PORT] endpoint."""
    default_port = _validate_port(default_port)
    if not raw:
        return default_host, default_port

    text = raw.strip()
    if not text:
        return default_host, default_port

    if ":" not in text:
        return text, default_port

    host, port_text = text.rsplit(":", 1)
    host = host.strip() or default_host
    if not port_text.strip():
        return host, default_port
    return host, _validate_port(int(port_text))


def format_discovery_message(name: str, port: int) -> str:
    """Build a UDP discovery announcement."""
    port = _validate_port(port)
    server_name = name.strip()
    if not server_name:
        raise ValueError("server name must not be empty")
    return f"{_DISCOVERY_PREFIX} {server_name} {port}"


def parse_discovery_message(message: str) -> tuple[str, int] | None:
    """Parse a UDP discovery announcement."""
    parts = message.strip().split()
    if len(parts) != 3 or parts[0] != _DISCOVERY_PREFIX:
        return None
    try:
        port = _validate_port(int(parts[2]))
    except ValueError:
        return None
    return parts[1], port
