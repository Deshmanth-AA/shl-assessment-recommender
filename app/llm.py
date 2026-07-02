import json
import os
import re
from openai import OpenAI

# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------

# Recommended models (choose one):
#   openai/gpt-oss-120b
#   moonshotai/kimi-k2-instruct
#   llama-3.3-70b-versatile
#
MODEL = os.environ.get(
    "SHL_AGENT_MODEL",
    "openai/gpt-oss-120b"
)

GROQ_BASE_URL = "https://api.groq.com/openai/v1"

_client = None


# -----------------------------------------------------------------------------
# Client
# -----------------------------------------------------------------------------

def _get_client():
    global _client

    if _client is None:
        api_key = os.environ.get("GROQ_API_KEY")

        if not api_key:
            raise RuntimeError(
                "GROQ_API_KEY is not set.\n"
                "Get one from https://console.groq.com/keys"
            )

        _client = OpenAI(
            api_key=api_key,
            base_url=GROQ_BASE_URL,
            timeout=20.0,
            max_retries=2,
        )

    return _client


# -----------------------------------------------------------------------------
# Robust JSON extraction
# -----------------------------------------------------------------------------

def _extract_json(text: str) -> dict:
    """
    Extract the first balanced JSON object from the model output.

    Handles:

    - ```json ... ```
    - extra explanations
    - stray text before/after JSON
    """

    text = text.strip()

    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text)
        text = re.sub(r"```$", "", text)
        text = text.strip()

    start = text.find("{")

    if start == -1:
        raise ValueError("No JSON object found.")

    depth = 0

    for i in range(start, len(text)):
        ch = text[i]

        if ch == "{":
            depth += 1

        elif ch == "}":
            depth -= 1

            if depth == 0:
                json_text = text[start:i + 1]
                return json.loads(json_text)

    raise ValueError("Unbalanced JSON.")


# -----------------------------------------------------------------------------
# Main LLM call
# -----------------------------------------------------------------------------

def call_agent_decision(
    system_prompt: str,
    user_prompt: str,
    max_tokens: int = 1200,
) -> dict:

    client = _get_client()

    response = client.chat.completions.create(
        model=MODEL,
        temperature=0,
        max_tokens=max_tokens,

        # Force JSON output
        response_format={
            "type": "json_object"
        },

        messages=[
            {
                "role": "system",
                "content": system_prompt,
            },
            {
                "role": "user",
                "content": user_prompt,
            },
        ],
    )

    raw = response.choices[0].message.content or ""

    try:
        return _extract_json(raw)

    except Exception as e:

        print("\n" + "=" * 80)
        print("FAILED TO PARSE LLM RESPONSE")
        print("=" * 80)
        print(raw)
        print("=" * 80)
        print(e)
        print("=" * 80 + "\n")

        # Safe fallback
        return {
            "action": "clarify",
            "reply": (
                "Could you tell me a bit more about the role "
                "and what you'd like the assessment to measure?"
            ),
            "assessment_ids": [],
            "end_of_conversation": False,
        }