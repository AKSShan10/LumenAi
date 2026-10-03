"""An offline stand-in for the AI model, used when LLM_PROVIDER=fake.

Use it for tests and for trying the app without an API key. Use a real model for the actual demo.
Each feature adds its own fake answer here, chosen by the prompt it sends, for example:

    if instructions == JOB_DESCRIPTION_PROMPT:
        return {"description": "..."}
"""


def fake_answer(instructions: str, data) -> dict:
    return {"ok": True}
