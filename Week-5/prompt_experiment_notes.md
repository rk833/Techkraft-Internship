# Week 5 - Prompt Engineering and Temperature Experiments

## Setup

For this week's practice, I used the Google Gemini API (`gemini-2.5-flash`). The scripts were updated to use Gemini and were executed successfully using a Python virtual environment.

The following packages were used:

```bash
google-genai
python-dotenv
```

API credentials were stored in a `.env` file and loaded securely using `python-dotenv`.

Two scripts were created:

* `compare_prompts.py`
* `test_temperature.py`

---

# Part 1: Compare Outputs with Different Prompts

## Objective

The goal of this exercise was to observe how changing the prompt affects the model's response, even when asking about the same topic.

The topic chosen was **overfitting in machine learning**.

---

## Prompt A — Vague

### Prompt

```text
Tell me about overfitting.
```

### Response Summary

The model generated a long and detailed explanation of overfitting. It covered:

* Definition of overfitting
* Causes of overfitting
* Characteristics of overfitting
* Detection methods
* Prevention techniques
* Differences between overfitting and underfitting

Since the prompt was very open-ended, the model decided on its own what information to include and how much detail to provide.

### Observation

The response was informative, but it covered much more information than was actually requested.

---

## Prompt B — Specific

### Prompt

```text
Explain overfitting in machine learning in 3-4 sentences.
Focus only on: what causes it and one common way to detect it.
```

### Response Summary

The response stayed within the requested scope and length.

The model explained that:

* Overfitting occurs when a model learns training data too closely.
* It is often caused by an overly complex model.
* A common way to detect it is by comparing training performance with validation or test performance.

The response avoided unrelated topics such as underfitting and prevention methods.

### Observation

Adding specific instructions significantly improved focus and reduced unnecessary information.

---

## Prompt C — Role + Constraint

### Prompt

```text
You are explaining overfitting to a first-year computer science student who has never trained a model before.
Use a simple real-world analogy.
Keep it under 60 words.
```

### Response Summary

The model used a student-exam analogy.

It compared overfitting to memorizing answers to practice questions instead of understanding the concepts behind them.

The explanation:

* Used simple language
* Avoided technical jargon
* Stayed within the requested word limit

### Observation

Providing a role and audience changed not only the tone but also the vocabulary used in the response.

---

## Comparison

| Aspect             | Vague Prompt | Specific Prompt | Role + Constraint Prompt |
| ------------------ | ------------ | --------------- | ------------------------ |
| Length             | Long         | Short           | Very Short               |
| Detail Level       | High         | Focused         | Simplified               |
| Jargon             | Moderate     | Moderate        | Minimal                  |
| Audience Awareness | None         | None            | High                     |
| Scope Control      | Low          | High            | High                     |

---

## Key Takeaways

* Prompt wording has a major impact on the quality and style of the response.
* Specific instructions help control the scope of the output.
* Adding a target audience changes how the model explains concepts.
* Constraints such as sentence limits and word limits are generally followed well.

---

# Part 2: Testing Temperature Effects

## Objective

The goal of this experiment was to observe how temperature affects the creativity and variability of model responses.

The same prompt was sent multiple times using different temperature values.

### Prompt

```text
Write exactly ONE opening sentence for a short story about a power outage in Kathmandu.
Return only the sentence and nothing else.
```

---

## Temperature = 0.0

### Outputs

Run 1:

> The sudden hush of the city, usually a symphony of generators and distant traffic, announced the familiar, unwelcome arrival of darkness across Kathmandu.

Run 2:

> The sudden hush of the city, usually a symphony of generators and distant traffic, announced the familiar, unwelcome arrival of darkness across Kathmandu.

Run 3:

> The sudden hush of the city, usually a symphony of generators and distant traffic, announced the familiar, unwelcome arrival of darkness across Kathmandu.

### Observation

All three outputs were identical.

This shows that temperature 0.0 produces highly predictable and deterministic responses.

---

## Temperature = 0.7

### Outputs

Run 1:

> The sudden, inky blackness swallowed Kathmandu whole, silencing the usual evening symphony of horns and distant prayers.

Run 2:

> The city's usual symphony of generators

Run 3:

> The familiar hum of the city died,

### Observation

The responses became more varied than at temperature 0.0.

Although two responses were unexpectedly truncated, the experiment still demonstrated increased diversity in wording and structure.

---

## Temperature = 1.0

### Outputs

Run 1:

> The city lights of Kathmandu blinked out, plunging the valley into an inky silence under a vast, star-strewn sky.

Run 2:

> The city of Kathmandu fell silent as the lights flickered and died, plunging the ancient valley into an unexpected darkness.

Run 3:

> The sudden, inky blanket of a power outage descended upon Kathmandu, silencing the usual hum and replacing it with an expectant hush.

### Observation

The outputs were the most creative and varied.

The model used more descriptive language and explored different ways of expressing the same idea.

---

## Temperature Comparison

| Temperature | Behavior                            |
| ----------- | ----------------------------------- |
| 0.0         | Highly predictable and repeatable   |
| 0.7         | Balanced creativity and consistency |
| 1.0         | Most creative and varied            |

---

## Key Takeaways

* Temperature controls randomness in model output.
* Lower temperatures produce more predictable responses.
* Higher temperatures produce more diverse and creative responses.
* For factual tasks, lower temperatures are generally safer.
* For brainstorming, storytelling, and creative writing, higher temperatures can be useful.

---

# Overall Reflection

This week's exercises showed that prompt engineering and temperature are two separate but important controls when working with large language models.

Prompt engineering determines what the model is asked to do, while temperature affects how predictably or creatively it responds.

From these experiments, I learned that:

* Well-structured prompts produce more focused and useful outputs.
* Audience and role instructions can significantly change the style of a response.
* Temperature directly influences response variability.
* Low temperature and specific prompts are better for factual tasks.
* Higher temperature settings are more suitable for creative tasks such as storytelling and idea generation.

These concepts will be useful in future AI projects, especially when building applications that require both reliable factual responses and creative content generation.
