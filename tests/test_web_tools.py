"""Tests for web tools (search and fetch)."""
import pytest
from unittest.mock import patch, MagicMock

from src.tools.web import search_web, fetch_web_page


class TestSearchWeb:
    """Tests for web search functionality."""
    
    def test_search_web_empty_query(self):
        """Test handling of empty search query."""
        result = search_web.invoke({"query": ""})
        assert "Error" in result
        assert "empty" in result.lower()
    
    def test_search_web_whitespace_query(self):
        """Test handling of whitespace-only query."""
        result = search_web.invoke({"query": "   "})
        assert "Error" in result
        assert "empty" in result.lower()
    
    def test_search_web_no_results(self):
        """Test handling when no results are found."""
        with patch.dict('sys.modules', {'ddgs': MagicMock()}):
            import sys
            mock_ddgs_instance = MagicMock()
            mock_ddgs_instance.text.return_value = []
            sys.modules['ddgs'].DDGS.return_value = mock_ddgs_instance
            
            result = search_web.invoke({"query": "extremely obscure query xyz123"})
            assert "No results found" in result
    
    def test_search_web_success(self):
        """Test successful web search with mocked results."""
        with patch.dict('sys.modules', {'ddgs': MagicMock()}):
            import sys
            mock_ddgs_instance = MagicMock()
            mock_ddgs_instance.text.return_value = [
                {"title": "Test Title", "href": "https://example.com", "body": "Test snippet"},
                {"title": "Another Result", "href": "https://example.org", "body": "More content"},
            ]
            sys.modules['ddgs'].DDGS.return_value = mock_ddgs_instance
            
            result = search_web.invoke({"query": "test query"})
            
            assert "Web Search" in result
            assert "Test Title" in result
            assert "https://example.com" in result
            assert "Test snippet" in result
    
    def test_search_web_max_results(self):
        """Test max_results parameter is passed correctly."""
        with patch.dict('sys.modules', {'ddgs': MagicMock()}):
            import sys
            mock_ddgs_instance = MagicMock()
            mock_ddgs_instance.text.return_value = []
            sys.modules['ddgs'].DDGS.return_value = mock_ddgs_instance
            
            search_web.invoke({"query": "test", "max_results": 10})
            
            mock_ddgs_instance.text.assert_called_once_with("test", max_results=10)


class TestFetchWebPage:
    """Tests for web page fetching functionality."""
    
    def test_fetch_web_page_empty_url(self):
        """Test handling of empty URL."""
        result = fetch_web_page.invoke({"url": ""})
        assert "Error" in result
        assert "empty" in result.lower()
    
    def test_fetch_web_page_invalid_url_format(self):
        """Test handling of invalid URL format."""
        result = fetch_web_page.invoke({"url": "not-a-valid-url"})
        assert "Error" in result
        assert "Invalid URL format" in result
    
    def test_fetch_web_page_ftp_protocol(self):
        """Test rejection of non-http protocols."""
        result = fetch_web_page.invoke({"url": "ftp://example.com/file"})
        assert "Error" in result
        assert "http://" in result or "https://" in result
    
    def test_fetch_web_page_success(self):
        """Test successful web page fetch with mocked response."""
        import requests
        from bs4 import BeautifulSoup
        
        with patch('requests.get') as mock_get:
            mock_response = MagicMock()
            mock_response.content = b"<html><body>Test content only text here</body></html>"
            mock_get.return_value = mock_response
            
            result = fetch_web_page.invoke({"url": "https://example.com"})
            
            assert "Web Page" in result
            assert "https://example.com" in result
    
    def test_fetch_web_page_request_error(self):
        """Test handling of request errors."""
        import requests
        
        with patch('requests.get') as mock_get:
            mock_get.side_effect = requests.exceptions.RequestException("Connection failed")
            
            result = fetch_web_page.invoke({"url": "https://unreachable-site.com"})
            
            assert "Error" in result
            assert "Failed to fetch" in result
    
    def test_fetch_web_page_truncation(self):
        """Test content truncation for long pages."""
        with patch('requests.get') as mock_get:
            mock_response = MagicMock()
            # Create long content
            mock_response.content = b"<html><body>" + b"X" * 20000 + b"</body></html>"
            mock_get.return_value = mock_response
            
            result = fetch_web_page.invoke({"url": "https://example.com", "max_length": 1000})
            
            assert "truncated" in result.lower()
