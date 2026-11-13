"""Model providers. Pick one with LLM_PROVIDER in .env: "gemini" or "anthropic".

complete() takes the system prompt and the chat so far and returns (text, usage).
"""
from . import config


def complete(system: str, messages: list[dict], model: str, max_tokens: int) -> tuple[str, dict]:
    if config.LLM_PROVIDER == "gemini":
        return _gemini(system, messages, model, max_tokens)
    if config.LLM_PROVIDER == "anthropic":
        return _anthropic(system, messages, model, max_tokens)
    raise ValueError(f"Unknown LLM_PROVIDER '{config.LLM_PROVIDER}'. Use 'gemini' or 'anthropic'.")


def _gemini(system, messages, model, max_tokens):
    from google import genai
    from google.genai import types

    client = genai.Client()  # reads GEMINI_API_KEY from the environment
    contents = [
        {"role": "model" if m["role"] == "assistant" else "user", "parts": [{"text": m["content"]}]}
        for m in messages
    ]
    response = client.models.generate_content(
        model=model,
        contents=contents,
        config=types.GenerateContentConfig(
            system_instruction=system,
            max_output_tokens=max_tokens,
            response_mime_type="application/json",
        ),
    )
    meta = response.usage_metadata
    usage = {
        "input_tokens": (meta.prompt_token_count or 0) if meta else 0,
        "output_tokens": ((meta.candidates_token_count or 0) + (getattr(meta, "thoughts_token_count", None) or 0))
        if meta else 0,
    }
    return response.text or "", usage


def _anthropic(system, messages, model, max_tokens):
    from anthropic import Anthropic

    client = Anthropic()  # reads ANTHROPIC_API_KEY from the environment
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": m["role"], "content": m["content"]} for m in messages],
    )
    text = "".join(block.text for block in response.content if block.type == "text")
    return text, {"input_tokens": response.usage.input_tokens, "output_tokens": response.usage.output_tokens}
