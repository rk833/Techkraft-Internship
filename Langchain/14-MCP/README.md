# Module 14 - MCP

**Status:** complete. Server and client both run, with the agent live.

## Goal

Expose capabilities over a protocol instead of importing them, so tools can live
in a separate program and be used by any client.

## Topics covered

| Topic | Where it appears |
|-------|------------------|
| MCP servers | `file_server.py` |
| MCP clients | `file_assistant.py` |
| Tools | `list_notes`, `read_note`, `search_notes` |
| Resources | `notes://{name}`, and the `resources` command |

## Files

| File | Purpose |
|------|---------|
| `file_server.py` | The MCP server. Standalone, knows nothing about LangChain. |
| `file_assistant.py` | The client. Discovers tools and gives them to an agent. |
| `notes/` | Four work notes, two of which deliberately disagree. |

## Setup

```powershell
pip install -r ..\requirements.txt
```

**`mcp` must stay below 2.0.** See the version note at the end.

## Running it

```powershell
python file_assistant.py tools
python file_assistant.py resources
python file_assistant.py call --tool list_notes
python file_assistant.py call --tool search_notes --args '{\"query\": \"retention\"}'
python file_assistant.py ask --question "who owns the staging database credentials, and when will they move to the vault"
```

| Command | Cost |
|---------|------|
| `tools` | none |
| `resources` | none |
| `call` | none |
| `ask` | one chat call per turn of the agent loop |

**Three of the four commands make no model call.** The server can be developed
and tested completely without spending quota, which is how it should be: a
broken tool is much easier to diagnose with `call` than through an agent.

You never start the server yourself. The client launches it as a subprocess.
Running `python file_server.py` directly looks like a hang, which is correct: it
is waiting for JSON-RPC on stdin.

## What you should see

### tools

```
the server offers 3 tool(s):

name: list_notes
    List the note files available to read. Call this first to see what exists.

name: read_note
    Read one note file in full. Pass a filename exactly as list_notes reported it.
    arg name (string)

name: search_notes
    Find which notes mention a word or phrase, with the matching lines.
    arg query (string)

this list was discovered at runtime by asking the server, not
imported from it. no model was called.
```

**`file_assistant.py` never imports `file_server.py`.** It starts it as a
subprocess and asks what it can do. The names, descriptions and argument schemas
all came over the wire.

### ask

```
question: who owns the staging database credentials, and when will they move to the vault
[3 tools loaded from the MCP server]

  calling search_notes({'query': 'staging database credentials'})
  -> meeting-2026-07-14.md:11: Open question: nobody knows who owns the staging...
  calling search_notes({'query': 'vault'})
  -> meeting-2026-07-21.md:8: They will be moved into the shared vault by 4 August.

The staging database credentials are owned by the data team (confirmed by
Marcus in meeting-2026-07-21.md). They are scheduled to be moved into the
shared vault by 4 August (meeting-2026-07-21.md).
```

The notes are written so this question has a trap. On 14 July the answer was
"nobody knows"; on 21 July it was resolved. The agent found both and preferred
the later one, which the system prompt asked it to do:

> If two notes disagree, say which is more recent and prefer it.

Without that line, models will happily quote a stale answer that is still
technically present in the source.

## Why this is different from Module 11

Module 11 defined tools as Python functions in the same file as the agent. They
worked, and they could only ever be used by that one program.

| | Module 11 | Module 14 |
|---|-----------|-----------|
| Where tools live | same process | separate program |
| How the agent finds them | `import` | asks over a protocol |
| Who else can use them | nobody | any MCP client |
| Language | Python only | anything that speaks MCP |
| Failure isolation | a crash takes the agent down | server crash is a subprocess dying |

The integration is this, and nothing else:

```python
SERVER_CONFIG = {
    "notes": {
        "command": sys.executable,
        "args": [str(SERVER)],
        "transport": "stdio",
    }
}
```

A command and a transport. Pointing at someone else's MCP server, written in
TypeScript or Go, means editing those two lines. That is the entire promise of
the protocol: tools stop being library code and become a service.

## Tools and resources are not the same thing

```powershell
python file_assistant.py resources
```

```
resources:
  none listed directly

resource templates:
  notes://{name}

reading notes://onboarding.md directly:
  # Getting set up
  Request access to the vault first, everything else depends on it...
```

- A **tool** is an action the model chooses to take, with arguments it fills in.
- A **resource** is content addressed by a URI, which the **client** reads
  directly. The model is not involved in the decision.

The server exposes `notes://{name}` as a **template** rather than a list of
fixed URIs, which is why it appears under templates and the direct list is
empty. The LangChain adapter converts tools into agent tools; resources are read
by the client, as the `resources` command does.

Roughly: resources are for content you already know you want, tools are for
letting the model decide.

## Path traversal, and why it matters more here

`resolve_path` refuses anything outside the notes folder:

```python
candidate = (NOTES_DIR / name).resolve()
if not candidate.is_relative_to(NOTES_DIR):
    raise ValueError(f"'{name}' is outside the notes folder")
```

Tested:

| Requested | Result |
|-----------|--------|
| `onboarding.md` | file contents |
| `../../.env` | `error: '../../.env' is outside the notes folder` |
| `../common/models.py` | `error: ... is outside the notes folder` |

The first attack targets the file holding your API key.

This is the same lesson as Module 11's calculator, and it applies harder here.
An MCP server is usually pointed at a real filesystem, and the filename arrives
from a language model that may be relaying whatever a user typed.

**Resolve first, then check containment.** Scanning the string for `..` before
resolving is not enough, because symlinks, absolute paths and unusual separators
get past a string check but not past a resolved-path comparison.

## Things that caused real problems

### mcp 2.0 breaks langchain-mcp-adapters

Installing the obvious way gives `mcp` 2.0.0, and the client fails at import:

```
ImportError: cannot import name 'RequestContext' from 'mcp.shared.context'
```

`langchain-mcp-adapters` 0.3.1 is written against `mcp` 1.x. Version 2.0 also
renamed the server class: `mcp.server.fastmcp.FastMCP` became
`mcp.server.MCPServer`, and `mcp.server.fastmcp` no longer exists.

`requirements.txt` therefore pins `mcp==1.29.0`, and the reason is written next
to the pin. If you install `mcp` yourself, use `pip install "mcp<2"`.

Worth noting how the failure presents: an import error naming a symbol you have
never heard of, in a package you did not install directly. That is almost always
a version mismatch between two packages rather than a bug in your code.

### asyncio.run inside a running event loop

MCP is async throughout, so `ask` is a coroutine. The first version called the
existing sync helper, which internally did `asyncio.run`:

```
Call to model 'gemini-3.1-flash-lite' failed: asyncio.run() cannot be called
from a running event loop
```

The fix was `arun_with_fallback` in `common/models.py`, an async twin of
`run_with_fallback` that awaits the action rather than bridging into it. Module
15 needs the same thing, since FastAPI handlers are async too.

You cannot bridge into a running loop from inside it. Either the whole path is
async or none of it is.

### MCP tool results are content blocks

`ainvoke` on an MCP tool returns a list, not a string:

```python
[{'type': 'text', 'text': '5', 'id': 'lc_0f351e73-...'}]
```

MCP allows a tool to return text, images or embedded resources, so the result is
always a list of typed blocks. `unwrap` flattens it for display. The agent
handles this itself, so it only matters for the `call` command.

Same shape as the content blocks in Module 01, for the same reason.


