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
    """Initialize the LLM by inferring the provider from the model name.
    
    Returns (None, None) if MODEL or MODEL_API_KEY are not set — the CLI will
    surface these as required settings before allowing a prompt to be submitted.
    """
    model = os.getenv("MODEL")
    if not model:
        return None, None
        
    provider = _infer_provider_from_model(model)
    api_key = os.getenv("MODEL_API_KEY")
    
    if not api_key:
        return None, None
    
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
    
    # OpenAI-compatible models that need a custom base URL.
    # Support both environment variable names for compatibility.
    base_url = os.getenv("API_BASE_URL") or os.getenv("OPENAI_API_BASE")
    if not base_url:
        raise ValueError(
            "API_BASE_URL environment variable is required for custom OpenAI-compatible "
            "models (non-gpt OpenAI-style endpoints)."
        )
    llm = ChatOpenAI(model=model, api_key=api_key, base_url=base_url)
    return llm, model


def _create_llm_for_model(model: str, api_key: str, base_url: str = None):
    """Create an LLM instance for a given model name, api key, and optional base URL."""
    provider = _infer_provider_from_model(model)
    
    if provider == "gemini":
        return ChatGoogleGenerativeAI(
            model=model,
            google_api_key=api_key,
            include_thoughts=True,
        )
    
    if provider == "claude":
        return ChatAnthropic(model=model, api_key=api_key, temperature=0.7)
    
    if provider == "grok":
        return ChatXAI(model=model, xai_api_key=api_key)
    
    if provider == "openai":
        return ChatOpenAI(model=model, api_key=api_key, stream_usage=True)
    
    # custom_openai
    if not base_url:
        raise ValueError(
            f"API base URL is required for custom OpenAI-compatible model '{model}'. "
            "Set the appropriate API_BASE_URL environment variable."
        )
    return ChatOpenAI(model=model, api_key=api_key, base_url=base_url)


def initialize_llm_for_agent(agent_name: str, fallback_llm=None, fallback_model_name=None):
    """Initialize an LLM for a specific agent, falling back to the primary model.
    
    Checks for {AGENT_NAME}_MODEL env var. If set, creates a dedicated LLM
    for that agent. Otherwise returns the fallback (primary) LLM.
    
    Args:
        agent_name: Agent name (e.g., 'strategist', 'operator', 'evaluator')
        fallback_llm: The primary LLM to fall back to
        fallback_model_name: The primary model name to fall back to
        
    Returns:
        Tuple of (llm, model_name)
    """
    prefix = agent_name.upper()
    model = os.getenv(f"{prefix}_MODEL")
    
    if not model:
        return fallback_llm, fallback_model_name
    
    # Agent-specific API key, falling back to the primary API key
    api_key = os.getenv(f"{prefix}_MODEL_API_KEY") or os.getenv("MODEL_API_KEY")
    if not api_key:
        raise ValueError(
            f"API key required for {agent_name} model '{model}'. "
            f"Set {prefix}_MODEL_API_KEY or MODEL_API_KEY."
        )
    
    # Agent-specific base URL, falling back to primary base URL
    base_url = (
        os.getenv(f"{prefix}_API_BASE_URL") 
        or os.getenv("API_BASE_URL") 
        or os.getenv("OPENAI_API_BASE")
    )
    
    llm = _create_llm_for_model(model, api_key, base_url)
    return llm, model
