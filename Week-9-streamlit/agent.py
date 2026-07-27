"""
agent.py
The agentic loop. This is the heart of "agentic RAG":

    1. Send the conversation + the search_docs tool to Gemini.
    2. Gemini replies with either:
         a) a function_call part -> it wants to search
         b) a text part -> it's ready to give a final answer
    3. If (a): run search_docs(), append the result back into the
       conversation as a function response, and go back to step 1.
    4. If (b): return the text to the user. Loop ends.

    A max_turns cap prevents infinite loops if something goes wrong.
"""

import os
from google import genai
from google.genai import types
from dotenv import load_dotenv

from tools import search_docs, rag_tool

load_dotenv()

MODEL_NAME = "gemini-2.5-flash"
MAX_TURNS = 5  # safety cap on how many times the agent can call the tool per question

SYSTEM_INSTRUCTION = (
    "You are a helpful Q&A assistant that answers questions using the "
    "search_docs tool, which searches content ingested from local "
    "documents. Always search before answering factual questions about "
    "the documents' content — never make up information. If search "
    "results don't contain the answer, say so honestly rather than "
    "guessing. Cite the source filename(s) you used at the end of your "
    "answer."
)

client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])


def run_agent(user_message: str, chat_history: list) -> tuple[str, list]:
    """
    Runs one full agentic turn.

    Args:
        user_message: the new question from the user
        chat_history: list of google.genai `Content` objects from prior turns
                       (pass [] for a fresh conversation)

    Returns:
        (final_answer_text, updated_chat_history)
    """
    contents = chat_history + [
        types.Content(role="user", parts=[types.Part(text=user_message)])
    ]

    for _ in range(MAX_TURNS):
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_INSTRUCTION,
                tools=[rag_tool],
            ),
        )

        candidate = response.candidates[0]
        contents.append(candidate.content)  # keep model's turn in history

        function_calls = [
            part.function_call for part in candidate.content.parts if part.function_call
        ]

        if not function_calls:
            # model gave a final text answer -> done
            final_text = "".join(
                part.text for part in candidate.content.parts if part.text
            )
            return final_text, contents

        # model wants to call search_docs (possibly more than once)
        response_parts = []
        for fc in function_calls:
            query = fc.args.get("query", "")
            result = search_docs(query)
            response_parts.append(
                types.Part.from_function_response(
                    name="search_docs",
                    response={"result": result},
                )
            )

        contents.append(types.Content(role="user", parts=response_parts))

    return "I wasn't able to settle on an answer within my search budget — try rephrasing your question.", contents
