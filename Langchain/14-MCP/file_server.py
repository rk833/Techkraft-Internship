"""
An MCP server exposing a folder of notes.

This is the server half of Module 14. It is a standalone program that speaks
Model Context Protocol over stdin and stdout, and it knows nothing about
LangChain, Gemini or agents. Any MCP client can use it.

That separation is the whole point of the protocol. Module 11 defined tools as
Python functions inside the same process as the agent, so they could only ever
be used by that agent. The same three functions exposed over MCP can be used by
any client that speaks the protocol, in any language.

Run it directly and it will sit waiting for JSON-RPC messages on stdin, which
looks like a hang. That is correct behaviour. It is meant to be launched by a
client, which is what file_assistant.py does.

Usage:
    python file_assistant.py ...     launches this automatically
    python file_server.py            starts it standalone, for an MCP client
"""

from pathlib import Path

from mcp.server.fastmcp import FastMCP

# Everything the server will ever read lives under here. Nothing outside it is
# reachable, which is enforced in resolve_path below.
NOTES_DIR = (Path(__file__).resolve().parent / "notes").resolve()

MAX_BYTES = 20_000

# log_level keeps the server's own INFO chatter off stderr, where it would
# otherwise interleave with the client's output
server = FastMCP("notes", log_level="WARNING")


def resolve_path(name: str) -> Path:
    """
    Turn a requested filename into a real path inside NOTES_DIR, or refuse.

    The argument arrives from a language model, so it is untrusted, exactly as
    in Module 11. Without this check a request for '../../.env' would be
    honoured, and an MCP server is often given access to a real filesystem.

    Resolving first and then checking containment is what makes it safe.
    Checking the string for '..' before resolving is not enough, because
    symlinks and odd separators get past it.
    """
    candidate = (NOTES_DIR / name).resolve()

    if not candidate.is_relative_to(NOTES_DIR):
        raise ValueError(f"'{name}' is outside the notes folder")
    if not candidate.exists() or not candidate.is_file():
        raise ValueError(f"'{name}' does not exist")

    return candidate


@server.tool()
def list_notes() -> str:
    """List the note files available to read. Call this first to see what exists."""
    files = sorted(p.name for p in NOTES_DIR.iterdir() if p.is_file())
    if not files:
        return "no notes found"
    return "\n".join(f"{name} ({(NOTES_DIR / name).stat().st_size} bytes)" for name in files)


@server.tool()
def read_note(name: str) -> str:
    """Read one note file in full. Pass a filename exactly as list_notes reported it."""
    try:
        path = resolve_path(name)
    except ValueError as error:
        return f"error: {error}"

    text = path.read_text(encoding="utf-8")
    if len(text) > MAX_BYTES:
        return text[:MAX_BYTES] + "\n[truncated]"
    return text


@server.tool()
def search_notes(query: str) -> str:
    """Find which notes mention a word or phrase, with the matching lines.

    Use this when you do not know which file holds the answer. Matching is
    case insensitive and plain text, not regular expressions.
    """
    needle = query.lower().strip()
    if not needle:
        return "error: empty query"

    results = []
    for path in sorted(NOTES_DIR.iterdir()):
        if not path.is_file():
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if needle in line.lower():
                results.append(f"{path.name}:{number}: {line.strip()}")

    if not results:
        return f"no notes mention '{query}'"
    return "\n".join(results[:40])


@server.resource("notes://{name}")
def note_resource(name: str) -> str:
    """
    Expose a note as an MCP resource.

    Resources and tools are different things in MCP. A tool is an action the
    model chooses to take. A resource is content addressed by URI that a client
    can read directly, more like a file than a function.

    The LangChain adapter converts tools into agent tools; resources are read by
    the client itself. file_assistant.py lists them with the 'resources' command.
    """
    return read_note(name)


if __name__ == "__main__":
    server.run()
