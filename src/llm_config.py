"""LLM configuration and initialization."""

import os

from .openai_compat import QuasarChatOpenAI as ChatOpenAI

ChatGoogleGenerativeAI = None
ChatAnthropic = None
ChatXAI = None


def _missing_provider_dependency(package_name: str, provider: str) -> ImportError:
    return ImportError(
        f"{package_name} is required for {provider} models. "
        "Install Python dependencies with `python3 -m pip install -r requirements.txt`."
    )


def _load_gemini_chat_model():
    global ChatGoogleGenerativeAI
    if ChatGoogleGenerativeAI is not None:
        return ChatGoogleGenerativeAI
    try:
        from langchain_google_genai import ChatGoogleGenerativeAI as _ChatGoogleGenerativeAI
    except ImportError as exc:
        raise _missing_provider_dependency("langchain-google-genai", "Gemini") from exc
    ChatGoogleGenerativeAI = _ChatGoogleGenerativeAI
    return ChatGoogleGenerativeAI


def _load_anthropic_chat_model():
    global ChatAnthropic
    if ChatAnthropic is not None:
        return ChatAnthropic
    try:
        from langchain_anthropic import ChatAnthropic as _ChatAnthropic
    except ImportError as exc:
        raise _missing_provider_dependency("langchain-anthropic", "Claude") from exc
    ChatAnthropic = _ChatAnthropic
    return ChatAnthropic


def _load_xai_chat_model():
    global ChatXAI
    if ChatXAI is not None:
        return ChatXAI
    try:
        from langchain_xai import ChatXAI as _ChatXAI
    except ImportError as exc:
        raise _missing_provider_dependency("langchain-xai", "Grok") from exc
    ChatXAI = _ChatXAI
    return ChatXAI


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
    
    If a custom base URL is set (API_BASE_URL or OPENAI_API_BASE), the
    OpenAI-compatible client is always used regardless of the model name.
    """
    model = os.getenv("MODEL")
    if not model:
        return None, None
        
    api_key = os.getenv("MODEL_API_KEY")
    
    if not api_key:
        return None, None
    
    os.environ["MODEL"] = model
    
    # If a custom base URL is provided, always route through the
    # OpenAI-compatible client — the user is pointing at a proxy/gateway.
    base_url = os.getenv("API_BASE_URL") or os.getenv("OPENAI_API_BASE")
    if base_url:
        llm = ChatOpenAI(
            model=model,
            api_key=api_key,
            base_url=base_url,
            stream_usage=True,
        )
        return llm, model
    
    provider = _infer_provider_from_model(model)
    
    if provider == "gemini":
        ChatGoogleGenerativeAI = _load_gemini_chat_model()
        llm = ChatGoogleGenerativeAI(
            model=model,
            google_api_key=api_key,
            include_thoughts=True,
        )
        return llm, model
    
    if provider == "claude":
        ChatAnthropic = _load_anthropic_chat_model()
        llm = ChatAnthropic(model=model, api_key=api_key, temperature=0.7)
        return llm, model
    
    if provider == "grok":
        ChatXAI = _load_xai_chat_model()
        llm = ChatXAI(model=model, xai_api_key=api_key)
        return llm, model
    
    if provider == "openai":
        llm = ChatOpenAI(model=model, api_key=api_key, stream_usage=True)
        return llm, model
    
    # Fallback: custom_openai without a base URL
    raise ValueError(
        "API_BASE_URL environment variable is required for custom OpenAI-compatible "
        "models (non-gpt OpenAI-style endpoints)."
    )


def _create_llm_for_model(model: str, api_key: str, base_url: str = None):
    """Create an LLM instance for a given model name, api key, and optional base URL.
    
    If base_url is provided, always uses ChatOpenAI (OpenAI-compatible mode)
    regardless of the model name.
    """
    # Custom base URL → always use OpenAI-compatible client
    if base_url:
        return ChatOpenAI(
            model=model,
            api_key=api_key,
            base_url=base_url,
            stream_usage=True,
        )
    
    provider = _infer_provider_from_model(model)
    
    if provider == "gemini":
        ChatGoogleGenerativeAI = _load_gemini_chat_model()
        return ChatGoogleGenerativeAI(
            model=model,
            google_api_key=api_key,
            include_thoughts=True,
        )
    
    if provider == "claude":
        ChatAnthropic = _load_anthropic_chat_model()
        return ChatAnthropic(model=model, api_key=api_key, temperature=0.7)
    
    if provider == "grok":
        ChatXAI = _load_xai_chat_model()
        return ChatXAI(model=model, xai_api_key=api_key)
    
    if provider == "openai":
        return ChatOpenAI(model=model, api_key=api_key, stream_usage=True)
    
    # custom_openai without a base URL
    raise ValueError(
        f"API base URL is required for custom OpenAI-compatible model '{model}'. "
        "Set the appropriate API_BASE_URL environment variable."
    )


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
