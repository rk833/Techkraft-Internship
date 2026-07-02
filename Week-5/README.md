# Week 5: LLM Basics

## Practice

* Compare outputs with different prompts
* Test temperature effects

## Deliverable

* Prompt experiment notes and examples

---

## Overview

This week focused on understanding how Large Language Models (LLMs) behave under different instructions and generation settings.

The main goals were:

* Observe how prompt wording affects model responses
* Understand the impact of temperature on output variability
* Explore the relationship between prompting, creativity, and hallucination risk
* Practice basic prompt engineering techniques

For this week's exercises, I used the Google Gemini API (`gemini-2.5-flash`) and implemented two Python scripts to run the experiments.

---

## Files

| File                         | Type        | Purpose                                                      |
| ---------------------------- | ----------- | ------------------------------------------------------------ |
| `prompt_experiment_notes.md` | Deliverable | Full write-up containing observations, outputs, and analysis |
| `compare_prompts.py`         | Practice    | Compares responses generated from different prompt styles    |
| `test_temperature.py`        | Practice    | Tests how temperature affects response variability           |
| `requirements.txt`           | Shared      | Project dependencies                                         |
| `.env.example`               | Setup       | Example environment variable configuration                   |

---

## Environment Setup

### Create a virtual environment

```bash
python -m venv .venv
```

### Activate the virtual environment

**Windows (PowerShell)**

```powershell
.\.venv\Scripts\Activate
```

**Mac/Linux**

```bash
source .venv/bin/activate
```

---

### Install dependencies

```bash
pip install -r requirements.txt
```

---

### Create a Gemini API key

Generate an API key from Google AI Studio.

Create a `.env` file in the project root:

```env
GEMINI_API_KEY=your_api_key_here
```

A sample file is provided:

```text
.env.example
```

---

## Project Structure

```text
Week-5/
│
├── .env
├── .env.example
├── .gitignore
├── requirements.txt
│
├── compare_prompts.py
├── test_temperature.py
│
└── prompt_experiment_notes.md
```

---

# Practice 1: Compare Outputs with Different Prompts

## Purpose

This script demonstrates how changing the wording of a prompt affects the model's response, even when asking about the same topic.

The topic used for testing was:

```text
Overfitting in machine learning
```

Three prompt styles were compared:

### 1. Vague Prompt

```text
Tell me about overfitting.
```

### 2. Specific Prompt

```text
Explain overfitting in machine learning in 3-4 sentences.
Focus only on: what causes it and one common way to detect it.
```

### 3. Role + Constraint Prompt

```text
You are explaining overfitting to a first-year computer science student who has never trained a model before.
Use a simple real-world analogy.
Keep it under 60 words.
```

## Run the Script

```bash
python compare_prompts.py
```

## What I Learned

* Prompt wording significantly changes response quality.
* Specific instructions help control scope and detail.
* Role-based prompts influence vocabulary and explanation style.
* Length constraints are generally followed well by the model.

More detailed analysis can be found in:

```text
prompt_experiment_notes.md
```

---

# Practice 2: Test Temperature Effects

## Purpose

This script demonstrates how temperature affects creativity, randomness, and consistency in model outputs.

The same prompt was executed multiple times at different temperature settings.

### Prompt

```text
Write exactly ONE opening sentence for a short story about a power outage in Kathmandu.
Return only the sentence and nothing else.
```

### Temperatures Tested

```python
[0.0, 0.7, 1.0]
```

## Run the Script

```bash
python test_temperature.py
```

## What I Learned

### Temperature 0.0

* Produced identical outputs across multiple runs
* Most predictable and deterministic

### Temperature 0.7

* Produced more variation
* Balanced creativity and consistency

### Temperature 1.0

* Produced the most creative and diverse outputs
* Used more descriptive language and varied phrasing

More detailed results are documented in:

```text
prompt_experiment_notes.md
```

---

# Deliverable

The main deliverable for this week is:

```text
prompt_experiment_notes.md
```

The document contains:

* Prompt comparison results
* Temperature experiment results
* Observations from both exercises
* Comparison tables
* Overall reflections and takeaways

---

# Key Concepts Covered

## Prompt Engineering

Learning how prompt wording influences:

* Response length
* Level of detail
* Vocabulary
* Structure
* Target audience

---

## Temperature

Understanding how temperature affects:

* Randomness
* Creativity
* Consistency
* Predictability

---

## Hallucination Risk

Understanding why:

* Vague prompts increase uncertainty
* Higher temperatures increase variation
* Combining both can make outputs less reliable

---

# Overall Reflection

This week's exercises showed that prompt engineering and temperature are two separate controls that influence model behavior.

Prompt engineering determines what the model is asked to do, while temperature affects how predictably or creatively it responds.

Through these experiments, I observed that:

* Well-structured prompts produce more focused outputs.
* Audience and role instructions can significantly change explanations.
* Lower temperatures are useful for factual and repeatable tasks.
* Higher temperatures are useful for brainstorming and creative writing.

These concepts will be important when building future AI applications that require both reliable factual responses and creative content generation.

