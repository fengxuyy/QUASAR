"""
LLM streaming utilities with token tracking and repetition detection.
"""

import json
import re
from collections import Counter
from typing import Callable, Optional

from .text import _extract_text, _extract_thoughts


class StopGenerationException(Exception):
    """Raised when generation should stop early due to repetition detection."""
    pass


class RepetitionDetector:
    """Detects repetitive patterns in streaming LLM output.
    
    Uses multiple detection strategies:
    1. N-gram repetition: Detects repeated phrases (sequences of words)
    2. Sliding window: Detects when recent output matches earlier output
    3. Character-level: Detects repeated character sequences (e.g., "!!!!!")
    4. Line-level: Detects when the same line/sentence is repeated multiple times
    5. Sentence-level: Detects exact duplicate sentences
    """
    
    def __init__(
        self,
        ngram_size: int = 4,
        ngram_threshold: int = 3,
        window_size: int = 100,
        similarity_threshold: float = 0.7,
        char_repeat_threshold: int = 10,
        min_content_length: int = 50,
        line_repeat_threshold: int = 3,
        sentence_repeat_threshold: int = 3,
    ):
        """Initialize the repetition detector.
        
        Args:
            ngram_size: Number of words in each n-gram to track
            ngram_threshold: Number of times an n-gram must appear to trigger detection
            window_size: Size of sliding window (in characters) for similarity checking
            similarity_threshold: Jaccard similarity threshold (0-1) for window comparison
            char_repeat_threshold: Number of repeated characters to trigger detection
            min_content_length: Minimum content length before detection activates
            line_repeat_threshold: Number of times a line must repeat to trigger detection
            sentence_repeat_threshold: Number of times a sentence must repeat to trigger detection
        """
        self.ngram_size = ngram_size
        self.ngram_threshold = ngram_threshold
        self.window_size = window_size
        self.similarity_threshold = similarity_threshold
        self.char_repeat_threshold = char_repeat_threshold
        self.min_content_length = min_content_length
        self.line_repeat_threshold = line_repeat_threshold
        self.sentence_repeat_threshold = sentence_repeat_threshold
        
        self._ngram_counts: Counter = Counter()
        self._sentence_counts: Counter = Counter()
        self._full_content = ""
        self._last_clean_position = 0
    
    def add_chunk(self, chunk: str) -> bool:
        """Add a chunk of text and check for repetition.
        
        Args:
            chunk: New text chunk to add
            
        Returns:
            True if repetition is detected, False otherwise
        """
        self._full_content += chunk
        
        # Check for character-level repetition FIRST (e.g., "!!!!!!" or "......")
        # This is checked regardless of content length since it's a clear indicator
        if self._check_char_repetition(chunk):
            return True
        
        # Don't check other patterns until we have enough content
        if len(self._full_content) < self.min_content_length:
            return False
        
        # Check for line-level repetition (same line repeated multiple times)
        if self._check_line_repetition():
            return True
        
        # Check for sentence-level repetition (same sentence repeated)
        if self._check_sentence_repetition():
            return True
        
        # Check for n-gram repetition
        if self._check_ngram_repetition():
            return True
        
        # Check sliding window similarity
        if self._check_sliding_window():
            return True
        
        return False
    
    def _check_char_repetition(self, chunk: str) -> bool:
        """Check for repeated character sequences in the recent chunk."""
        # Pattern matches any character repeated N+ times
        pattern = rf'(.)\1{{{self.char_repeat_threshold - 1},}}'
        return bool(re.search(pattern, chunk))
    
    def _check_line_repetition(self) -> bool:
        """Check if any line is repeated too many times.
        
        This catches patterns like:
        > I'll call `complete_task`.
        > I'll call `complete_task`.
        > I'll call `complete_task`.
        """
        lines = self._full_content.split('\n')
        line_counts: Counter = Counter()
        
        for line in lines:
            # Normalize the line (strip whitespace, lowercase)
            normalized = line.strip().lower()
            if len(normalized) >= 10:  # Only count substantial lines
                line_counts[normalized] += 1
                if line_counts[normalized] >= self.line_repeat_threshold:
                    return True
        
        return False
    
    def _check_sentence_repetition(self) -> bool:
        """Check if any sentence is repeated too many times.
        
        This catches patterns like:
        "I'll call complete_task.I'll call complete_task.I'll call complete_task."
        even when they're concatenated without newlines.
        """
        # Split on sentence boundaries (., !, ?)
        # Handle cases where sentences run together
        content = self._full_content
        
        # Split by common sentence endings, keeping the delimiter
        sentences = re.split(r'(?<=[.!?])\s*', content)
        
        self._sentence_counts.clear()
        for sentence in sentences:
            # Normalize the sentence
            normalized = sentence.strip().lower()
            if len(normalized) >= 10:  # Only count substantial sentences
                self._sentence_counts[normalized] += 1
                if self._sentence_counts[normalized] >= self.sentence_repeat_threshold:
                    return True
        
        return False
    
    def _check_ngram_repetition(self) -> bool:
        """Check if any n-gram appears too many times."""
        # Tokenize into words (simple split, handles most cases)
        words = self._full_content.lower().split()
        
        if len(words) < self.ngram_size:
            return False
        
        # Only check new n-grams since last check
        start_idx = max(0, len(words) - self.ngram_size - 10)
        
        # Build n-grams
        self._ngram_counts.clear()
        for i in range(len(words) - self.ngram_size + 1):
            ngram = tuple(words[i:i + self.ngram_size])
            self._ngram_counts[ngram] += 1
            
            if self._ngram_counts[ngram] >= self.ngram_threshold:
                return True
        
        return False
    
    def _check_sliding_window(self) -> bool:
        """Check if recent window is too similar to earlier content."""
        content_len = len(self._full_content)
        
        if content_len < self.window_size * 2:
            return False
        
        # Get recent window and compare to earlier windows
        recent_window = self._full_content[-self.window_size:].lower()
        recent_words = set(recent_window.split())
        
        # Check against several earlier windows
        for offset in range(self.window_size, content_len - self.window_size, self.window_size // 2):
            earlier_window = self._full_content[offset:offset + self.window_size].lower()
            earlier_words = set(earlier_window.split())
            
            # Jaccard similarity
            if recent_words and earlier_words:
                intersection = len(recent_words & earlier_words)
                union = len(recent_words | earlier_words)
                similarity = intersection / union if union > 0 else 0
                
                if similarity >= self.similarity_threshold:
                    return True
        
        return False
    
    def get_clean_content(self) -> str:
        """Get the content up to where repetition was detected.
        
        Returns the full content minus the last repeated portion.
        """
        # Try to find where the repetition started and return content before that
        content = self._full_content
        
        # Find the last complete sentence before potential repetition
        # Look for sentence endings in the last portion
        last_portion = content[-(self.window_size * 2):] if len(content) > self.window_size * 2 else content
        
        # Find last sentence boundary in the earlier part
        sentence_endings = ['.', '!', '?', '\n\n']
        best_end = len(content) - len(last_portion)
        
        for ending in sentence_endings:
            pos = content.rfind(ending, 0, len(content) - self.window_size // 2)
            if pos > best_end:
                best_end = pos + len(ending)
        
        return content[:best_end].strip() if best_end > 0 else content.strip()


def stream_with_token_tracking(
    llm_instance,
    messages: list,
    on_content: Optional[Callable[[str], None]] = None,
    on_thought: Optional[Callable[[str], None]] = None,
    detect_repetition: bool = False,
    repetition_config: Optional[dict] = None,
) -> tuple:
    """Stream LLM response with proper chunk accumulation for token tracking.
    
    This is the standard streaming helper for all agents (except analyze_image).
    It handles:
    - Text content streaming with callback
    - Thought content streaming with callback (provider-specific)
    - Tool call chunk accumulation
    - Response chunk accumulation for usage_metadata
    - Token usage tracking via record_api_call
    - Optional repetition detection with early stopping
    
    Args:
        llm_instance: LangChain LLM instance (with or without tools)
        messages: List of messages to send
        on_content: Optional callback called with each text chunk for live streaming
        on_thought: Optional callback called with each thought chunk for live streaming
        detect_repetition: If True, monitors for repetitive output and stops early
        repetition_config: Optional dict to customize RepetitionDetector settings:
            - ngram_size (int): Words per n-gram (default: 4)
            - ngram_threshold (int): Repetitions to trigger (default: 3)
            - window_size (int): Sliding window chars (default: 100)
            - similarity_threshold (float): Jaccard threshold (default: 0.7)
            - char_repeat_threshold (int): Repeated chars to trigger (default: 10)
            - min_content_length (int): Min chars before detection (default: 50)
        
    Returns:
        tuple: (full_content, tool_calls, aggregated_response, was_stopped_early)
            - full_content: Complete text content as string (cleaned if stopped early)
            - tool_calls: List of tool call dicts with 'name', 'id', 'args'
            - aggregated_response: The accumulated response object (for advanced use)
            - was_stopped_early: True if generation was stopped due to repetition
    """
    from ...usage_tracker import record_api_call
    
    full_content = ""
    accumulated_tool_calls = {}
    full_response = None
    was_stopped_early = False
    
    # Initialize repetition detector if enabled
    detector = None
    if detect_repetition:
        config = repetition_config or {}
        detector = RepetitionDetector(
            ngram_size=config.get('ngram_size', 4),
            ngram_threshold=config.get('ngram_threshold', 3),
            window_size=config.get('window_size', 100),
            similarity_threshold=config.get('similarity_threshold', 0.7),
            char_repeat_threshold=config.get('char_repeat_threshold', 10),
            min_content_length=config.get('min_content_length', 50),
        )
    
    try:
        for chunk in llm_instance.stream(messages):
            # Extract text content
            if hasattr(chunk, 'content') and chunk.content:
                thought_chunk = _extract_thoughts(chunk.content)
                if thought_chunk and on_thought:
                    on_thought(thought_chunk)
                chunk_text = _extract_text(chunk.content)
                if chunk_text:
                    full_content += chunk_text
                    if on_content:
                        on_content(chunk_text)
                    
                    # Check for repetition if detection is enabled
                    if detector and detector.add_chunk(chunk_text):
                        # Repetition detected - stop generation and get clean content
                        full_content = detector.get_clean_content()
                        was_stopped_early = True
                        break
            
            # Accumulate tool call chunks
            if hasattr(chunk, 'tool_call_chunks') and chunk.tool_call_chunks:
                for tc_chunk in chunk.tool_call_chunks:
                    idx = tc_chunk.get('index', 0)
                    if idx not in accumulated_tool_calls:
                        accumulated_tool_calls[idx] = {
                            'name': tc_chunk.get('name'),
                            'args': tc_chunk.get('args') or '',
                            'id': tc_chunk.get('id')
                        }
                    else:
                        if tc_chunk.get('name'):
                            accumulated_tool_calls[idx]['name'] = tc_chunk['name']
                        if tc_chunk.get('args'):
                            accumulated_tool_calls[idx]['args'] += tc_chunk['args']
                        if tc_chunk.get('id'):
                            accumulated_tool_calls[idx]['id'] = tc_chunk['id']
            
            # Accumulate chunks for usage_metadata
            if full_response is None:
                full_response = chunk
            else:
                full_response = full_response + chunk
    except Exception as e:
        # Handle empty response errors from LangChain (e.g., "must contain either output text or tool calls")
        error_msg = str(e)
        if "empty" in error_msg.lower() or "must contain" in error_msg.lower():
            # Return empty results - caller should handle this gracefully
            pass
        else:
            raise
    
    # Track token usage from aggregated response
    if full_response and hasattr(full_response, 'usage_metadata') and full_response.usage_metadata:
        usage = full_response.usage_metadata
        # Handle both dict and object access patterns
        if isinstance(usage, dict):
            input_tokens = usage.get('input_tokens', 0)
            output_tokens = usage.get('output_tokens', 0)
        else:
            input_tokens = getattr(usage, 'input_tokens', 0)
            output_tokens = getattr(usage, 'output_tokens', 0)
        record_api_call(
            input_tokens=input_tokens,
            output_tokens=output_tokens
        )
    
    # Convert accumulated tool calls to list format
    tool_calls = []
    for idx, tc_data in accumulated_tool_calls.items():
        tc_name = tc_data.get('name')
        tc_id = tc_data.get('id')
        tc_args_str = tc_data.get('args', '')
        
        if not tc_name:
            continue
        
        parsed_args = {}
        if tc_args_str:
            try:
                parsed_args = json.loads(tc_args_str)
            except json.JSONDecodeError:
                pass
        
        tool_calls.append({
            'name': tc_name,
            'id': tc_id,
            'args': parsed_args
        })
    
    return full_content, tool_calls, full_response, was_stopped_early
