"""Shared AI helpers used by several features.

    llm_client.py   the only place that talks to the AI model (Gemini by default)
    fake_llm.py     offline stand-in for tests and trying the app without a key

The prompts of the LangGraph workflows live next to each graph in app/graphs/.
"""
