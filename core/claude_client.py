"""
Claude Client Wrapper - Clean abstraction over the SDK
Handles all the message parsing and API interaction
"""

import re
import json
import base64
from pathlib import Path
from typing import Optional, Dict, Any, Union


class ClaudeClient:
    """
    Wrapper around Claude Agent SDK that provides a clean interface
    Handles all the message object parsing internally
    """
    
    def __init__(self, debug: bool = False):
        self.debug = debug
        
    async def query(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """
        Send a query to Claude and get back clean text response

        Args:
            prompt: The user prompt
            system_prompt: Optional system prompt (not supported in simple query API)

        Returns:
            Clean text response from Claude

        Raises:
            ImportError: If neither Claude Agent SDK nor Anthropic SDK is available
        """
        # If system prompt provided, prepend it
        if system_prompt:
            full_prompt = f"{system_prompt}\n\n{prompt}"
        else:
            full_prompt = prompt

        response_text = ""

        if self.debug:
            print(f"\n[DEBUG] Sending prompt ({len(full_prompt)} chars)")

        # Try Claude Agent SDK first
        try:
            from claude_agent_sdk import query
            async for message in query(prompt=full_prompt):
                text = self._extract_text_from_message(message)
                if text:
                    response_text += text
        except ImportError:
            # Fall back to Anthropic SDK
            try:
                import anthropic
                import os

                api_key = os.getenv("ANTHROPIC_API_KEY")
                if not api_key:
                    raise ValueError(
                        "ANTHROPIC_API_KEY environment variable not set. "
                        "For testing without API keys, use MockClaudeClient from tests.mocks"
                    )

                client = anthropic.Anthropic(api_key=api_key)
                response = client.messages.create(
                    model="claude-sonnet-4-20250514",
                    max_tokens=4096,
                    messages=[{"role": "user", "content": full_prompt}]
                )
                response_text = response.content[0].text
            except ImportError:
                raise ImportError(
                    "Neither claude-agent-sdk nor anthropic SDK is installed. "
                    "Install one with: pip install anthropic\n"
                    "For testing without API keys, use MockClaudeClient from tests.mocks"
                )

        if self.debug:
            print(f"[DEBUG] Received response ({len(response_text)} chars)")
            print(f"[DEBUG] First 500 chars:")
            print(response_text[:500])
            print("[DEBUG] ---")

        return response_text.strip()

    async def query_with_image(
        self,
        prompt: str,
        image_path: Union[str, Path],
        system_prompt: Optional[str] = None
    ) -> str:
        """
        Send a query to Claude with an image for vision analysis

        Args:
            prompt: The user prompt
            image_path: Path to the image file (local path or URL)
            system_prompt: Optional system prompt

        Returns:
            Clean text response from Claude

        Raises:
            FileNotFoundError: If image file doesn't exist
            ValueError: If image format is not supported
            ImportError: If Anthropic SDK is not available
        """
        image_path = Path(image_path)

        # Validate image exists
        if not image_path.exists():
            raise FileNotFoundError(f"Image not found: {image_path}")

        # Read and encode image
        image_data = image_path.read_bytes()
        image_b64 = base64.standard_b64encode(image_data).decode("utf-8")

        # Determine media type from extension
        extension = image_path.suffix.lower()
        media_type_map = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".gif": "image/gif",
            ".webp": "image/webp"
        }
        media_type = media_type_map.get(extension)
        if not media_type:
            raise ValueError(f"Unsupported image format: {extension}")

        if self.debug:
            print(f"\n[DEBUG] Sending vision query with image: {image_path.name}")
            print(f"[DEBUG] Image size: {len(image_data)} bytes")

        # Vision queries require direct Anthropic SDK
        try:
            import anthropic
            import os

            api_key = os.getenv("ANTHROPIC_API_KEY")
            if not api_key:
                raise ValueError(
                    "ANTHROPIC_API_KEY environment variable not set. "
                    "Vision queries require the Anthropic SDK."
                )

            client = anthropic.Anthropic(api_key=api_key)

            # Build message content with image
            message_content = [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": media_type,
                        "data": image_b64,
                    },
                },
                {
                    "type": "text",
                    "text": prompt
                }
            ]

            # Create message with vision
            response = client.messages.create(
                model="claude-sonnet-4-20250514",  # Supports vision
                max_tokens=4096,
                messages=[{"role": "user", "content": message_content}],
                system=system_prompt if system_prompt else None
            )

            response_text = response.content[0].text

            if self.debug:
                print(f"[DEBUG] Received vision response ({len(response_text)} chars)")

            return response_text.strip()

        except ImportError:
            raise ImportError(
                "anthropic SDK is required for vision queries. "
                "Install with: pip install anthropic"
            )

    def _extract_text_from_message(self, message) -> str:
        """Extract text content from Claude SDK message objects"""
        
        # Try to access message attributes directly first (most reliable)
        # This avoids string parsing issues
        
        # Check for content attribute (list of content blocks)
        if hasattr(message, 'content') and message.content:
            if isinstance(message.content, list):
                texts = []
                for item in message.content:
                    if hasattr(item, 'text'):
                        texts.append(item.text)
                if texts:
                    return '\n'.join(texts)
            elif isinstance(message.content, str):
                return message.content
        
        # Check for result attribute (final result)
        if hasattr(message, 'result'):
            result = message.result
            if isinstance(result, str):
                return result
        
        # Fallback to string parsing (less reliable due to escaping issues)
        msg_str = str(message)
        
        # Skip system initialization messages
        if 'SystemMessage' in msg_str and 'subtype' in msg_str:
            return ""
        
        # Look for ResultMessage - but be careful with escaping
        # We need to extract the actual result value, not the escaped string repr
        if hasattr(message, '__dict__'):
            if 'result' in message.__dict__:
                return str(message.__dict__['result'])
        
        return ""


class JSONExtractor:
    """Utility to extract JSON from Claude responses"""
    
    @staticmethod
    def extract(response: str, debug: bool = False) -> Dict[str, Any]:
        """
        Extract JSON from Claude response, handling various formats
        
        Args:
            response: Raw text response from Claude
            debug: Print debug info if True
            
        Returns:
            Parsed JSON dict
            
        Raises:
            ValueError: If no valid JSON found
        """
        if not response or not response.strip():
            raise ValueError("Empty response")
        
        response = response.strip()
        
        if debug:
            print(f"\n[JSON EXTRACT DEBUG] Response length: {len(response)}")
            print(f"[JSON EXTRACT DEBUG] First 300 chars:\n{response[:300]}")
        
        # Try markdown code blocks first (most common)
        json_match = re.search(
            r'```(?:json)?\s*\n(.*?)\n```', 
            response, 
            re.DOTALL | re.IGNORECASE
        )
        if json_match:
            json_str = json_match.group(1).strip()
            if debug:
                print(f"[JSON EXTRACT DEBUG] Found code block, length: {len(json_str)}")
            try:
                return json.loads(json_str)
            except json.JSONDecodeError as e:
                if debug:
                    print(f"[JSON EXTRACT DEBUG] Code block parse failed: {e}")
                    print(f"[JSON EXTRACT DEBUG] Problematic JSON:\n{json_str}")
                # Try to fix common issues
                # Remove any backslash escapes that aren't valid JSON escapes
                json_str_fixed = re.sub(r'\\(?!["\\/bfnrtu])', r'\\\\', json_str)
                try:
                    return json.loads(json_str_fixed)
                except json.JSONDecodeError:
                    pass
        
        # Try to find JSON object anywhere in the text
        json_match = re.search(r'\{.*\}', response, re.DOTALL)
        if json_match:
            json_str = json_match.group(0)
            try:
                return json.loads(json_str)
            except json.JSONDecodeError:
                pass
        
        # Try parsing the whole response as JSON
        try:
            return json.loads(response)
        except json.JSONDecodeError as e:
            raise ValueError(
                f"No valid JSON found in response.\n"
                f"Error: {e}\n"
                f"Response preview: {response[:300]}"
            )
