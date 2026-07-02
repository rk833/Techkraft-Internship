"""
Week 5 Practice: Compare Outputs with Different Prompts

Compares how prompt wording changes model responses.

Requirements:
    pip install google-genai python-dotenv

Create a .env file:
    GEMINI_API_KEY=your_api_key_here
"""

import os

from dotenv import load_dotenv
from google import genai

# Load .env variables
load_dotenv()

MODEL = "gemini-2.5-flash"

PROMPTS = {
    "vague": "Tell me about overfitting.",
    "specific": (
        "Explain overfitting in machine learning in 3-4 sentences. "
        "Focus only on: what causes it and one common way to detect it."
    ),
    "role_and_constraint": (
        "You are explaining overfitting to a first-year computer "
        "science student who has never trained a model before. "
        "Use a simple real-world analogy. Keep it under 60 words."
    ),
}


def get_response(client, prompt_text):
    """Send a prompt and return the model response."""

    response = client.models.generate_content(
        model=MODEL,
        contents=prompt_text,
    )

    return response.text


def main():
    api_key = os.getenv("GEMINI_API_KEY")

    if not api_key:
        print("Error: GEMINI_API_KEY not found.")
        print("Add it to your .env file.")
        return

    client = genai.Client(api_key=api_key)

    print("\nComparing Prompt Styles\n")

    for label, prompt_text in PROMPTS.items():
        print("=" * 70)
        print(f"PROMPT STYLE : {label}")
        print("=" * 70)
        print(f"PROMPT:\n{prompt_text}")
        print("-" * 70)

        try:
            response_text = get_response(client, prompt_text)

            print("RESPONSE:")
            print(response_text)

        except Exception as error:
            print(f"Request failed: {error}")

        print("\n")

    print("Done.")


if __name__ == "__main__":
    main()