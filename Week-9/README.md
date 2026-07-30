# Week 9: Agent Basics

## Practice
- Build a small tool-using assistant
- Test simple tool calls

## Deliverable
- Basic agent demo

## Overview
Week 9 introduces agents — the core idea being that the model *decides*
what to do next, rather than always following the same fixed pipeline.

| | Chatbot (Weeks 5–8) | Agent (this week) |
|---|---|---|
| Flow | always: input → LLM → output | input → LLM → maybe tool → LLM → output |
| Tools | none (or always retrieval) | model chooses whether and which tool |
| Control | deterministic pipeline | model plans the action |

UI is built with **Rich** — colored panels, tables, and inline tool
call notifications in the terminal. No browser, no extra server.

## Files
| File | Type | Covers |
|---|---|---|
| `tools.py` | Shared | Tool implementations (no API key needed) |
| `tool_test.py` | Practice | Test all tools in isolation with a Rich results table |
| `agent.py` | Practice + **Deliverable** | Interactive agent with Rich UI |
| `requirements.txt` | — | Dependencies |
| `.env.example` / `.gitignore` | — | Key setup, keeps `.env` and `notes.json` out of git |

---

## Setup

```bash
pip install -r requirements.txt
copy .env.example .env        # Windows
# cp .env.example .env        # Mac/Linux
```
Open `.env`, replace `your-key-here` with your Gemini key from
[aistudio.google.com](https://aistudio.google.com) (free, no card needed).

---

## Practice: Test Simple Tool Calls (`tool_test.py`)

Tests all tools directly — no agent loop, no API key needed.
Outputs a Rich table with a ✓/✗ status for each case, including
edge cases (unsupported units, blocked `__import__` injection attempt).

**Run it:**
```bash
python tool_test.py
```

**Real output:**
```
──────────────────── Week 9 — Tool Tests ────────────────────

                     Tool Test Results
╭───────────────┬──────────────────────┬──────────────┬────────╮
│ Tool          │ Description          │ Output       │ Status │
├───────────────┼──────────────────────┼──────────────┼────────┤
│ calculate     │ power                │ 2**10 = 1024 │ ✓ PASS │
│ calculate     │ square root          │ sqrt(144)... │ ✓ PASS │
│ calculate     │ blocks __import__    │ Could not... │ ✓ PASS │
│ convert_units │ 100 km → miles       │ 100 km = ... │ ✓ PASS │
│ convert_units │ 25 celsius → fahr... │ 25°C = 77... │ ✓ PASS │
│ save_note     │ save two notes       │ Note 'Shop.. │ ✓ PASS │
│ list_notes    │ list after saving    │ Saved note.. │ ✓ PASS │
│ ...           │ ...                  │ ...          │ ✓ PASS │
╰───────────────┴──────────────────────┴──────────────┴────────╯

╭──────────────────────────────────────────────────╮
│ All tests passed.                                │
│ Tools are verified and ready for the agent.      │
╰──────────────────────────────────────────────────╯
```

Why test tools before the agent? When something breaks in an agent
loop, you need to know whether the tool is broken or the model called
it wrong. Testing in isolation rules out one of those immediately.

---

## Practice + Deliverable: Basic Agent Demo (`agent.py`)

**Run it:**
```bash
python agent.py
```

The startup screen shows available tools and example prompts in Rich
panels. The agent loop then:
- Takes your typed question
- Gemini decides whether a tool is needed and which one
- Shows a `→ tool: <name>  args...` line if a tool was called
- Prints the response in a cyan panel

**Tools:**
| Tool | Does |
|---|---|
| `calculate` | math: `sqrt`, `**`, `pi`, `%`, etc. |
| `convert_units` | km/miles, °C/°F/K, kg/lbs, m/feet |
| `save_note` | persists to `notes.json` |
| `list_notes` | lists saved note titles |

**Example session:**
```
You: what is 2 to the power of 16?

  → tool: calculate  expression='2**16'
╭─────────── Agent ───────────╮
│ 2 to the power of 16 is     │
│ 65,536.                      │
╰─────────────────────────────╯

You: convert 30 celsius to fahrenheit

  → tool: convert_units  value=30.0, from_unit='celsius', to_unit='fahrenheit'
╭─────────── Agent ───────────╮
│ 30°C = 86.00°F              │
╰─────────────────────────────╯

You: what is the capital of Nepal?
╭─────────── Agent ───────────╮
│ The capital of Nepal is     │
│ Kathmandu.                  │
╰─────────────────────────────╯
```

The last example is the key one: no tool was called because the
model recognized it didn't need one — it answered from its own
knowledge instead. This illustrates "when NOT to use an agent"
from this week's topics.

## What this covers from Week 9
- **What an AI agent is** — the planning loop in `agent.py`
- **Chatbot vs agent** — the comparison table above
- **Tool use and function calling** — Gemini's automatic function
  calling reads Python docstrings to decide when/how to call each tool
- **Planning and action loops** — model decides per-turn whether to
  call a tool, which one, and with what args
- **When to use agents and when not to** — the "capital of Nepal"
  prompt shows the agent skipping tools entirely when not needed;
  the notes tools show conditional action (save only when asked)

## Why Rich instead of Streamlit
Rich adds colored panels, tables, and structured output directly in
the terminal — zero extra server, no browser needed, and the scripts
stay single-file Python. For internship weekly demos this is the right
call: low overhead, polished output, easy to run anywhere. Streamlit
(or Gradio) makes more sense for the Week 12 capstone where you want
a shareable public-facing UI.


