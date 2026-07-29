"""
Find a Gemini model name that works with your API key.

Model names change over time, so use this to pick a value for GEMINI_MODEL in
your .env file instead of copying one from a tutorial.

    python list_models.py           list models the API advertises
    python list_models.py --probe   send a tiny request to each one to see
                                    which are actually usable

The probe matters because a model can be advertised by the list endpoint and
still be unusable: retired models return 404, and older models can be dropped
from the free tier, which shows up as a 429 with a quota limit of 0.

Usage:
    python list_models.py --probe
"""

import argparse
import os
import sys
import time

from dotenv import load_dotenv

load_dotenv()

# probing every advertised model would waste quota and take a long time, so
# only ordinary text models are tried. image, speech, robotics and long running
# research models are skipped.
SKIP_MARKERS = (
    "image",
    "tts",
    "audio",
    "robotics",
    "computer-use",
    "lyria",
    "nano-banana",
    "deep-research",
    "antigravity",
)

SECONDS_BETWEEN_PROBES = 2


def text_model_names(client) -> list:
    """Names of advertised models that support ordinary text generation."""
    names = []
    for model in client.models.list():
        actions = getattr(model, "supported_actions", None) or []
        if "generateContent" not in actions:
            continue
        # the API returns names like "models/gemini-x"; strip the prefix
        names.append(model.name.removeprefix("models/"))
    return names


def probe(client, name: str) -> str:
    """Send the smallest possible request and report what happened."""
    from google.genai import types

    try:
        client.models.generate_content(
            model=name,
            contents="hi",
            config=types.GenerateContentConfig(max_output_tokens=5),
        )
        return "usable"
    except Exception as error:
        text = str(error)
        if "limit: 0" in text:
            return "no free tier quota"
        if "RESOURCE_EXHAUSTED" in text:
            return "rate limited, try again later"
        if "NOT_FOUND" in text:
            return "retired"
        return type(error).__name__


def main() -> int:
    parser = argparse.ArgumentParser(
        description="List or probe the Gemini models available to your API key."
    )
    parser.add_argument(
        "--probe",
        action="store_true",
        help="send a tiny request to each candidate to see which work",
    )
    args = parser.parse_args()

    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        print("GOOGLE_API_KEY is not set. Copy .env.example to .env and add your key.")
        return 1

    from google import genai

    client = genai.Client(api_key=api_key)
    names = text_model_names(client)

    if not args.probe:
        print("models advertised as supporting text generation:")
        for name in names:
            print("  " + name)
        print()
        print("being listed here does not mean the model is usable.")
        print("run with --probe to check.")
        return 0

    candidates = [n for n in names if not any(m in n for m in SKIP_MARKERS)]

    print(f"probing {len(candidates)} text models, this takes a moment")
    print()

    usable = []
    for name in candidates:
        result = probe(client, name)
        print(f"  {result:<28} {name}")
        if result == "usable":
            usable.append(name)
        time.sleep(SECONDS_BETWEEN_PROBES)

    print()
    if usable:
        print("set one of these as GEMINI_MODEL in .env:")
        for name in usable:
            print("  " + name)
    else:
        print("no usable models found. check your key and billing at")
        print("https://aistudio.google.com/apikey")

    return 0


if __name__ == "__main__":
    sys.exit(main())
