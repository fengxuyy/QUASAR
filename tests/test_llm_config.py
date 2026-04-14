"""Tests for LLM configuration and initialization."""
import pytest
import os
import sys
from unittest.mock import patch, MagicMock

# Mock langchain dependencies that may not be installed
if 'langchain_xai' not in sys.modules:
    sys.modules['langchain_xai'] = MagicMock()
if 'langchain_anthropic' not in sys.modules:
    sys.modules['langchain_anthropic'] = MagicMock()
if 'langchain_google_genai' not in sys.modules:
    sys.modules['langchain_google_genai'] = MagicMock()

from src.llm_config import _infer_provider_from_model, initialize_llm


class TestInferProvider:
    """Test provider inference from model names."""
    
    def test_infer_provider_gemini(self):
        """Test detecting Gemini models."""
        assert _infer_provider_from_model("gemini-2.5-pro") == "gemini"
        assert _infer_provider_from_model("gemini-2.5-flash") == "gemini"
        assert _infer_provider_from_model("GEMINI-3-PRO") == "gemini"
    
    def test_infer_provider_claude(self):
        """Test detecting Claude models."""
        assert _infer_provider_from_model("claude-sonnet-4-5") == "claude"
        assert _infer_provider_from_model("claude-opus-4") == "claude"
        assert _infer_provider_from_model("CLAUDE-HAIKU") == "claude"
    
    def test_infer_provider_grok(self):
        """Test detecting Grok models."""
        assert _infer_provider_from_model("grok-4-0709") == "grok"
        assert _infer_provider_from_model("grok-4-fast-reasoning") == "grok"
        assert _infer_provider_from_model("GROK-BETA") == "grok"
    
    def test_infer_provider_openai(self):
        """Test detecting native OpenAI GPT models."""
        assert _infer_provider_from_model("gpt-5") == "openai"
        assert _infer_provider_from_model("gpt-4o") == "openai"
        assert _infer_provider_from_model("GPT-5-MINI") == "openai"
    
    def test_infer_provider_custom_openai(self):
        """Test fallback to custom_openai for unknown models."""
        assert _infer_provider_from_model("llama-3-70b") == "custom_openai"
        assert _infer_provider_from_model("mistral-large") == "custom_openai"
        assert _infer_provider_from_model("qwen-72b") == "custom_openai"
    
    def test_infer_provider_empty_or_none(self):
        """Test handling of empty or None model names."""
        assert _infer_provider_from_model("") == "custom_openai"
        assert _infer_provider_from_model(None) == "custom_openai"


class TestInitializeLLM:
    """Test LLM initialization."""
    
    def test_initialize_llm_missing_model(self):
        """Test that missing MODEL returns a disabled client."""
        with patch.dict(os.environ, {}, clear=True):
            assert initialize_llm() == (None, None)

    def test_initialize_llm_missing_api_key(self):
        """Test that missing API key returns a disabled client."""
        with patch.dict(os.environ, {"MODEL": "gemini-2.5-pro"}, clear=True):
            assert initialize_llm() == (None, None)
    
    @patch('src.llm_config.ChatGoogleGenerativeAI')
    def test_initialize_llm_gemini(self, mock_gemini):
        """Test Gemini LLM initialization."""
        mock_llm = MagicMock()
        mock_gemini.return_value = mock_llm
        
        with patch.dict(os.environ, {"MODEL": "gemini-2.5-pro", "MODEL_API_KEY": "test-key"}):
            llm, model = initialize_llm()
            
            assert llm == mock_llm
            assert model == "gemini-2.5-pro"
            mock_gemini.assert_called_once()
    
    @patch('src.llm_config.ChatAnthropic')
    def test_initialize_llm_claude(self, mock_claude):
        """Test Claude LLM initialization."""
        mock_llm = MagicMock()
        mock_claude.return_value = mock_llm
        
        with patch.dict(os.environ, {"MODEL": "claude-sonnet-4", "MODEL_API_KEY": "test-key"}):
            llm, model = initialize_llm()
            
            assert llm == mock_llm
            assert model == "claude-sonnet-4"
            mock_claude.assert_called_once()
    
    @patch('src.llm_config.ChatOpenAI')
    def test_initialize_llm_custom_openai_missing_base_url(self, mock_openai):
        """Test custom OpenAI-compatible model requires base URL."""
        with patch.dict(os.environ, {"MODEL": "llama-3-70b", "MODEL_API_KEY": "test-key"}, clear=True):
            with pytest.raises(ValueError, match="API_BASE_URL environment variable is required"):
                initialize_llm()
    
    @patch('src.llm_config.ChatOpenAI')
    def test_initialize_llm_custom_openai_with_base_url(self, mock_openai):
        """Test custom OpenAI-compatible model with base URL."""
        mock_llm = MagicMock()
        mock_openai.return_value = mock_llm
        
        with patch.dict(os.environ, {
            "MODEL": "llama-3-70b",
            "MODEL_API_KEY": "test-key",
            "API_BASE_URL": "http://localhost:8000"
        }):
            llm, model = initialize_llm()
            
            assert llm == mock_llm
            mock_openai.assert_called_once_with(
                model="llama-3-70b",
                api_key="test-key",
                base_url="http://localhost:8000",
                stream_usage=True,
            )


class TestInitializeLLMForAgent:
    """Test per-agent LLM initialization."""
    
    def test_fallback_when_no_agent_env_var(self):
        """When no agent-specific MODEL is set, should return fallback."""
        from src.llm_config import initialize_llm_for_agent
        
        mock_llm = MagicMock()
        with patch.dict(os.environ, {}, clear=True):
            llm, model = initialize_llm_for_agent("strategist", mock_llm, "primary-model")
            assert llm is mock_llm
            assert model == "primary-model"
    
    @patch('src.llm_config.ChatGoogleGenerativeAI')
    def test_agent_override_uses_dedicated_model(self, mock_gemini):
        """When STRATEGIST_MODEL is set, should create a new LLM."""
        mock_agent_llm = MagicMock()
        mock_gemini.return_value = mock_agent_llm
        
        from src.llm_config import initialize_llm_for_agent
        
        mock_primary_llm = MagicMock()
        with patch.dict(os.environ, {
            "STRATEGIST_MODEL": "gemini-2.5-flash",
            "MODEL_API_KEY": "primary-key"
        }, clear=True):
            llm, model = initialize_llm_for_agent("strategist", mock_primary_llm, "primary-model")
            assert llm is mock_agent_llm
            assert model == "gemini-2.5-flash"
            mock_gemini.assert_called_once()
    
    @patch('src.llm_config.ChatAnthropic')
    def test_agent_specific_api_key(self, mock_claude):
        """When agent-specific API key is set, it should be used over primary."""
        mock_agent_llm = MagicMock()
        mock_claude.return_value = mock_agent_llm
        
        from src.llm_config import initialize_llm_for_agent
        
        with patch.dict(os.environ, {
            "OPERATOR_MODEL": "claude-sonnet-4",
            "MODEL_API_KEY": "primary-key",
            "OPERATOR_MODEL_API_KEY": "operator-key"
        }, clear=True):
            llm, model = initialize_llm_for_agent("operator", MagicMock(), "primary")
            mock_claude.assert_called_once_with(
                model="claude-sonnet-4",
                api_key="operator-key",
                temperature=0.7
            )
    
    def test_agent_override_missing_api_key_raises(self):
        """When agent model is set but no API key is available, should raise."""
        from src.llm_config import initialize_llm_for_agent
        
        with patch.dict(os.environ, {
            "EVALUATOR_MODEL": "gemini-2.5-pro"
        }, clear=True):
            with pytest.raises(ValueError, match="API key required"):
                initialize_llm_for_agent("evaluator", MagicMock(), "primary")
