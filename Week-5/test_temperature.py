"""
Week 5 Practice: Test Temperature Effects

Sends the SAME prompt to Gemini multiple times using different
temperature settings to observe how temperature affects output
creativity and variability.

Requirements:
    pip install google-genai python-dotenv

Create a .env file:
    GEMINI_API_KEY=your_api_key_here
"""

import os

from dotenv import load_dotenv
from google import genai
from google.genai import types

# Load variables from .env
load_dotenv()

MODEL = "gemini-2.5-flash"

PROMPT = (
    "Write exactly ONE opening sentence for a short story about a "
    "power outage in Kathmandu. "
    "Return only the sentence and nothing else."
)

TEMPERATURES = [0.0, 0.7, 1.0]
RUNS_PER_TEMPERATURE = 3


def get_response(client, prompt_text, temperature):
    """Generate a response using a specific temperature."""

    response = client.models.generate_content(
        model=MODEL,
        contents=prompt_text,
        config=types.GenerateContentConfig(
            temperature=temperature,
            max_output_tokens=200,
        ),
    )

    # Safely extract text
    if hasattr(response, "text") and response.text:
        return response.text.strip()

    return "[No text returned]"


def main():
    api_key = os.getenv("GEMINI_API_KEY")

    if not api_key:
        print("Error: GEMINI_API_KEY not found.")
        print("Create a .env file containing:")
        print("GEMINI_API_KEY=your_api_key_here")
        return

    client = genai.Client(api_key=api_key)

    print("\n" + "=" * 70)
    print("TEMPERATURE EXPERIMENT")
    print("=" * 70)
    print(f"\nPROMPT:\n{PROMPT}\n")

    for temperature in TEMPERATURES:
        print("=" * 70)
        print(f"TEMPERATURE = {temperature}")
        print("=" * 70)

        for run_number in range(1, RUNS_PER_TEMPERATURE + 1):
            try:
                response_text = get_response(
                    client,
                    PROMPT,
                    temperature,
                )

                print(f"\nRun {run_number}:")
                print(response_text)

            except Exception as error:
                print(f"\nRun {run_number}:")
                print(f"Request failed: {error}")

        print("\n")

    print("Experiment complete.")


if __name__ == "__main__":
    main()