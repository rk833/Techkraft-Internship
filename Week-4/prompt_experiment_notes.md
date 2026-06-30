# Week 4 — Prompt Experiment Notes

Part of the Week 4 deliverable: experimenting with prompts and noting
observations, tied to the "Intro to AI, ML, and LLMs" topic.

## What I tested

I gave an LLM the same underlying request three different ways to see
how prompt phrasing changes the output.

### 1. Vague prompt
**Prompt:** "Tell me about weather APIs."

**Observation:** Response was broad and generic — listed several APIs
(OpenWeatherMap, Open-Meteo, WeatherAPI) with no depth on any one of
them. Useful for discovery, not for building something.

### 2. Specific, scoped prompt
**Prompt:** "Compare Open-Meteo and OpenWeatherMap for a beginner
Python project. Focus on: do they need an API key, what's the free
tier limit, and how simple is the JSON response structure?"

**Observation:** Much more usable. The response stayed on the three
criteria I asked about instead of wandering into pricing tiers or
enterprise features I didn't ask for.

### 3. Role + constraint prompt
**Prompt:** "You are helping a beginner Python student. Explain how to
call the Open-Meteo current weather endpoint in under 100 words, and
include one code example."

**Observation:** Output length and tone matched the constraint. This
is the version closest to what I actually used while building
`weather_cli.py`.

## Takeaways

- **Specificity matters more than length.** The scoped prompt (#2)
  wasn't much longer than the vague one (#1), but it produced a far
  more targeted answer.
- **Constraints shape output, not just content.** Adding "under 100
  words" and "beginner" in prompt #3 changed vocabulary choice and
  example complexity, not just length.
- **Context window awareness:** longer back-and-forth prompt sessions
  start to include earlier turns as context. For a short, single-shot
  task like this one, that wasn't an issue — but it's worth remembering
  for multi-step tasks (relevant for RAG/agent work coming up in
  Month 2–3).
- **Temperature (read about, not directly testable in chat UI):** lower
  temperature favors consistent, predictable outputs (good for code
  generation); higher temperature favors variety (good for brainstorming).
  This maps to why the role+constraint prompt felt more "deterministic"
  in style than the vague one.