# Week 4: Git, APIs, and AI Introduction

## Practice
- Push code to GitHub
- Call a public API
- Experiment with prompts

## Deliverable
- Simple API-based Python project

## Overview
This week covers Git/GitHub basics, calling APIs with Python, and an
intro to AI/LLM concepts. Below, the practice exercises and the final
deliverable are kept separate, since they exercise different skills.

## Files
| File | Type | Covers |
|---|---|---|
| `weather_cli.py` | **Deliverable** | Full API-based Python project |
| `api_practice.py` | Practice | Call a public API |
| `prompt_experiment_notes.md` | Practice | Experiment with prompts |
| `github_push_log.md` | Practice | Push code to GitHub |
| `requirements.txt` | Shared | Dependencies for both scripts |

---

## Practice: Call a Public API (`api_practice.py`)
A small, standalone script with one job: hit an API and read the JSON
back. Uses GitHub's public API (no key required) to fetch basic info
for a username.

**Run it:**
```bash
python api_practice.py torvalds
```
Or with no argument, it will prompt you:
```bash
python api_practice.py
```

**Example output:**
```
------------------------------
Username:    torvalds
Name:        Linus Torvalds
Bio:         None
Public repos:8
Followers:   270000+
------------------------------
```

**Note on rate limits:** GitHub's API allows **60 anonymous requests
per hour, tracked by IP address** not per script or per key. If 
seen a `403 rate limit exceeded` error, it means that quota has been
used up (easy to do while testing repeatedly), not that something is
broken. Wait an hour, or read about authenticated requests (which get
a much higher limit) in [GitHub's API docs](https://docs.github.com/rest/overview/resources-in-the-rest-api#rate-limiting).

This is deliberately separate from the weather CLI different API,
much smaller scope so "call a public API" has its own standalone
evidence of practice rather than only existing inside the deliverable.

---

## Practice: Experiment with Prompts (`prompt_experiment_notes.md`)
Notes comparing a vague prompt vs. a scoped prompt vs. a role/constraint
prompt, with observations on how phrasing changed the output. See the
file for full detail.

---

## Practice: Push Code to GitHub (`github_push_log.md`)
A checklist + the actual commands used to commit and push this week's
work. This is a workflow exercise, not code the point is doing the
git cycle, not producing a file.

---

## Deliverable: Weather CLI (`weather_cli.py`)

A command-line weather lookup tool. Calls a free public API, parses
the JSON response, and prints a readable weather report for any city.

### What it does
1. Takes a city name (as a command-line argument or typed input)
2. Looks up the city's coordinates using Open-Meteo's geocoding API
3. Fetches current weather for those coordinates
4. Prints temperature, wind speed, conditions, and observation time

### Setup
```bash
pip install -r requirements.txt
```

### Usage
```bash
python weather_cli.py Kathmandu
```

Or run with no arguments and enter a city when prompted:
```bash
python weather_cli.py
```

### Example output
```
----------------------------------------
Weather report for Kathmandu, Nepal
----------------------------------------
Temperature:  24.3°C
Wind speed:   8.1 km/h
Conditions:   Partly cloudy
Observed at:  2026-06-24T12:00
----------------------------------------
```

### API used
[Open-Meteo](https://open-meteo.com/): free, no API key or signup
required, which kept the focus on Python and API handling rather than
authentication setup.

### What this covers from Week 4
- Calling a public API with Python (`requests`)
- Working with JSON responses
- Basic error handling (network failures, city not found)
