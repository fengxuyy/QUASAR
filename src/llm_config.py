"""LLM configuration and initialization."""

import os
from langchain_openai import ChatOpenAI
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_anthropic import ChatAnthropic
from langchain_xai import ChatXAI



def _infer_provider_from_model(model_name: str) -> str:
    """Infer which provider to use from the requested model name.
    
    Returns one of:
        - "gemini"       → Google Generative AI (Gemini)
        - "claude"       → Anthropic Claude
        - "grok"         → xAI Grok via langchain-xai
        - "openai"       → Native OpenAI (gpt-*)
        - "custom_openai"→ Any other OpenAI-compatible endpoint (requires API_BASE_URL)
    """
    normalized = (model_name or "").lower()
    if "gemini" in normalized:
        return "gemini"
    if "claude" in normalized:
        return "claude"
    if "grok" in normalized:
        return "grok"
    if "gpt" in normalized:
        return "openai"
    return "custom_openai"



def initialize_llm():
    """Initialize the LLM by inferring the provider from the model name."""
    model = os.getenv("MODEL")
    if not model:
        raise ValueError("MODEL environment variable is required.")
        
    provider = _infer_provider_from_model(model)
    api_key = os.getenv("MODEL_API_KEY")
    
    if not api_key:
        raise ValueError("MODEL_API_KEY environment variable is required.")
    
    os.environ["MODEL"] = model
    
    if provider == "gemini":
        llm = ChatGoogleGenerativeAI(
            model=model,
            google_api_key=api_key,
            include_thoughts=True,
        )
        return llm, model
    
    if provider == "claude":
        llm = ChatAnthropic(model=model, api_key=api_key, temperature=0.7)
        return llm, model
    
    if provider == "grok":
        llm = ChatXAI(model=model, xai_api_key=api_key)
        return llm, model
    
    if provider == "openai":
        llm = ChatOpenAI(model=model, api_key=api_key, stream_usage=True)
        return llm, model
    
    # OpenAI-compatible models that need a custom base URL
    # Check both API_BASE_URL and OPENAI_API_BASE (web UI uses OPENAI_API_BASE)
    base_url = os.getenv("API_BASE_URL") or os.getenv("OPENAI_API_BASE")
    if not base_url:
        raise ValueError(
            "API_BASE_URL environment variable is required for custom OpenAI-compatible "
            "models (non-gpt OpenAI-style endpoints)."
        )
    llm = ChatOpenAI(model=model, api_key=api_key, base_url=base_url)
    return llm, model

