from langchain_core.tools import tool

@tool
def search_web(query: str, max_results: int = 5) -> str:
    """Search the web and return structured results with URLs for each result.
    
    This tool returns search results with URLs, allowing you to identify and access
    specific web pages. Use this when you need to:
    - Find specific web pages or resources
    - Access full content from a particular website
    - Get URLs to share or reference
    
    Args:
        query: The search query string
        max_results: Maximum number of results to return (default: 5)
    
    Returns:
        A formatted string listing search results with titles, URLs, and snippets.
        Format:
        [Result 1]
        Title: <title>
        URL: <url>
        Snippet: <snippet>
        
        [Result 2]
        ...
    """
    if not query or not query.strip():
        return "Error: Search query cannot be empty. Please provide a non-empty search query."
    
    try:
        from ddgs import DDGS
        results = list(DDGS().text(query, max_results=max_results))
        
        if not results:
            return f"No results found for query: '{query}'"
        
        formatted_results = []
        for i, result in enumerate(results, 1):
            snippet = result.get('body', 'No snippet available')
            formatted_results.append(
                f"> **[Result {i}]**\n"
                f"> **Title:** {result.get('title', 'No title')}\n"
                f"> **URL:** {result.get('href', 'No URL')}\n"
                f"> **Snippet:**\n```\n{snippet}\n```"
            )
        return f"**Web Search:** \"{query}\"\n\n" + "\n\n".join(formatted_results)
    except ImportError:
        return "Error: 'ddgs' package is required. Install with: pip install -U ddgs"
    except Exception as e:
        return f"Error: Web search failed: {str(e)}"


@tool
def fetch_web_page(url: str, max_length: int = 7000) -> str:
    """Fetch and parse the content of a web page using BeautifulSoup.
    
    Use this tool after search_web to get the full content of a specific web page.
    The tool extracts the main text content, removing navigation, ads, and other non-content elements.
    
    Args:
        url: The URL of the web page to fetch
        max_length: Maximum length of content to return in characters (default: 7000)
    
    Returns:
        The main text content of the web page, cleaned and formatted.
    """
    if not url or not url.strip():
        return "Error: URL cannot be empty."
    
    if not (url.startswith('http://') or url.startswith('https://')):
        return f"Error: Invalid URL format. URL must start with http:// or https://. Got: {url}"
    
    try:
        import requests
        from bs4 import BeautifulSoup
        
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        for element in soup(["script", "style", "nav", "header", "footer", "aside"]):
            element.decompose()
        
        text = soup.get_text()
        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        text = '\n'.join(chunk for chunk in chunks if chunk)
        
        if len(text) > max_length:
            text = text[:max_length] + f"\n\n... (truncated, total length: {len(text)} characters)"
        
        # Format with code block
        return f"**Web Page:** {url}\n\n```\n{text}\n```"
    except ImportError:
        return "Error: Required packages not available. Install with: pip install requests beautifulsoup4"
    except requests.exceptions.RequestException as e:
        return f"Error: Failed to fetch URL: {str(e)}"
    except Exception as e:
        return f"Error: Failed to parse web page: {str(e)}"

