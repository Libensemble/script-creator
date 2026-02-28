"""LLM factory — supports OpenAI, Anthropic, and compatible endpoints."""

import os
import sys


def create_llm(model, temperature=0, base_url=None):
    """Create LLM — ChatAnthropic for Claude models, ChatOpenAI otherwise."""
    if "claude" in model.lower():
        try:
            from langchain_anthropic import ChatAnthropic
        except ImportError:
            sys.exit("Error: pip install langchain-anthropic required for Claude models")
        anthropic_base = os.environ.get("ANTHROPIC_BASE_URL")
        return ChatAnthropic(
            model=model, temperature=temperature, base_url=anthropic_base or None
        )
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(model=model, temperature=temperature, base_url=base_url)
