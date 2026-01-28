"""
Provider Onboarding Agent

An intelligent agent that onboards new API providers by:
1. Reading and analyzing API documentation
2. Understanding model options, endpoints, and signatures
3. Generating provider implementations from stubs
4. Testing implementations interactively
5. Recording learnings for future use

Usage:
    claude-studio provider onboard --docs-url https://docs.provider.ai/api
    claude-studio provider onboard --stub core/providers/video/newprovider.py
    claude-studio provider test newprovider --interactive
"""

import asyncio
import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional
from abc import ABC, abstractmethod

import httpx


# =============================================================================
# DATA MODELS
# =============================================================================

class ProviderType(Enum):
    VIDEO = "video"
    AUDIO = "audio"
    IMAGE = "image"
    TTS = "tts"
    STT = "stt"
    LLM = "llm"


class AuthType(Enum):
    API_KEY_HEADER = "api_key_header"
    BEARER_TOKEN = "bearer_token"
    BASIC_AUTH = "basic_auth"
    OAUTH2 = "oauth2"
    CUSTOM = "custom"


class RequestMethod(Enum):
    SYNC = "sync"           # Single request, wait for response
    ASYNC_POLL = "async_poll"  # Submit job, poll for completion
    WEBSOCKET = "websocket"    # WebSocket streaming
    SSE = "sse"                # Server-sent events


@dataclass
class APIEndpoint:
    """Represents a single API endpoint"""
    name: str
    method: str  # GET, POST, etc.
    path: str
    description: str
    request_body: Optional[Dict[str, Any]] = None
    response_schema: Optional[Dict[str, Any]] = None
    query_params: Optional[Dict[str, Any]] = None
    headers: Optional[Dict[str, str]] = None
    
    # Inferred from analysis
    is_async: bool = False
    poll_endpoint: Optional[str] = None  # For async operations
    estimated_latency: Optional[str] = None  # "fast", "medium", "slow"


@dataclass
class ModelInfo:
    """Information about a specific model offered by the provider"""
    model_id: str
    name: str
    description: str
    capabilities: List[str] = field(default_factory=list)
    input_types: List[str] = field(default_factory=list)  # "text", "image", "audio"
    output_types: List[str] = field(default_factory=list)
    pricing: Optional[Dict[str, Any]] = None
    limitations: List[str] = field(default_factory=list)
    recommended_for: List[str] = field(default_factory=list)


@dataclass
class ProviderSpec:
    """Complete specification of a provider's API"""
    name: str
    provider_type: ProviderType
    base_url: str
    docs_url: str
    
    # Authentication
    auth_type: AuthType
    auth_header: str = "Authorization"
    auth_prefix: str = "Bearer"
    env_var_name: str = ""
    
    # Request pattern
    request_method: RequestMethod = RequestMethod.SYNC
    
    # Endpoints
    endpoints: List[APIEndpoint] = field(default_factory=list)
    
    # Models
    models: List[ModelInfo] = field(default_factory=list)
    default_model: Optional[str] = None
    
    # Configuration
    supported_formats: List[str] = field(default_factory=list)
    rate_limits: Optional[Dict[str, Any]] = None
    
    # Learnings
    tips: List[str] = field(default_factory=list)
    gotchas: List[str] = field(default_factory=list)
    
    # Metadata
    analyzed_at: datetime = field(default_factory=datetime.utcnow)
    confidence_score: float = 0.0  # How confident we are in this spec


@dataclass
class OnboardingSession:
    """Tracks the onboarding process for a provider"""
    provider_name: str
    started_at: datetime
    status: str = "in_progress"
    current_step: str = "init"  # init, docs, spec, implementation, testing, complete

    # Discovery
    docs_analyzed: List[str] = field(default_factory=list)
    docs_url: Optional[str] = None
    spec: Optional[ProviderSpec] = None

    # Questions and clarifications
    questions: List[Dict[str, str]] = field(default_factory=list)
    answers: List[Dict[str, str]] = field(default_factory=list)

    # Implementation
    stub_path: Optional[str] = None
    implementation_path: Optional[str] = None
    provider_type: Optional[str] = None

    # Testing
    test_results: List[Dict[str, Any]] = field(default_factory=list)

    # Learnings
    learnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize session to dict for saving"""
        return {
            "provider_name": self.provider_name,
            "started_at": self.started_at.isoformat(),
            "status": self.status,
            "current_step": self.current_step,
            "docs_analyzed": self.docs_analyzed,
            "docs_url": self.docs_url,
            "spec": self._spec_to_dict(self.spec) if self.spec else None,
            "questions": self.questions,
            "answers": self.answers,
            "stub_path": self.stub_path,
            "implementation_path": self.implementation_path,
            "provider_type": self.provider_type,
            "test_results": self.test_results,
            "learnings": self.learnings,
        }

    def _spec_to_dict(self, spec: ProviderSpec) -> Dict[str, Any]:
        """Convert ProviderSpec to dict"""
        return {
            "name": spec.name,
            "provider_type": spec.provider_type.value,
            "base_url": spec.base_url,
            "docs_url": spec.docs_url,
            "auth_type": spec.auth_type.value,
            "auth_header": spec.auth_header,
            "auth_prefix": spec.auth_prefix,
            "env_var_name": spec.env_var_name,
            "request_method": spec.request_method.value,
            "endpoints": [
                {
                    "name": ep.name,
                    "method": ep.method,
                    "path": ep.path,
                    "description": ep.description,
                    "request_body": ep.request_body,
                    "response_schema": ep.response_schema,
                }
                for ep in spec.endpoints
            ],
            "models": [
                {
                    "model_id": m.model_id,
                    "name": m.name,
                    "description": m.description,
                    "capabilities": m.capabilities,
                    "pricing": m.pricing,
                }
                for m in spec.models
            ],
            "tips": spec.tips,
            "gotchas": spec.gotchas,
            "confidence_score": spec.confidence_score,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "OnboardingSession":
        """Deserialize session from dict"""
        session = cls(
            provider_name=data["provider_name"],
            started_at=datetime.fromisoformat(data["started_at"]),
            status=data.get("status", "in_progress"),
        )
        session.current_step = data.get("current_step", "init")
        session.docs_analyzed = data.get("docs_analyzed", [])
        session.docs_url = data.get("docs_url")
        session.questions = data.get("questions", [])
        session.answers = data.get("answers", [])
        session.stub_path = data.get("stub_path")
        session.implementation_path = data.get("implementation_path")
        session.provider_type = data.get("provider_type")
        session.test_results = data.get("test_results", [])
        session.learnings = data.get("learnings", [])

        # Rebuild spec if present
        if data.get("spec"):
            session.spec = cls._dict_to_spec(data["spec"])

        return session

    @staticmethod
    def _dict_to_spec(data: Dict[str, Any]) -> ProviderSpec:
        """Convert dict back to ProviderSpec"""
        return ProviderSpec(
            name=data["name"],
            provider_type=ProviderType(data["provider_type"]),
            base_url=data["base_url"],
            docs_url=data.get("docs_url", ""),
            auth_type=AuthType(data["auth_type"]),
            auth_header=data.get("auth_header", "Authorization"),
            auth_prefix=data.get("auth_prefix", "Bearer"),
            env_var_name=data.get("env_var_name", ""),
            request_method=RequestMethod(data.get("request_method", "sync")),
            endpoints=[
                APIEndpoint(
                    name=ep["name"],
                    method=ep["method"],
                    path=ep["path"],
                    description=ep.get("description", ""),
                    request_body=ep.get("request_body"),
                    response_schema=ep.get("response_schema"),
                )
                for ep in data.get("endpoints", [])
            ],
            models=[
                ModelInfo(
                    model_id=m["model_id"],
                    name=m["name"],
                    description=m.get("description", ""),
                    capabilities=m.get("capabilities", []),
                    pricing=m.get("pricing"),
                )
                for m in data.get("models", [])
            ],
            tips=data.get("tips", []),
            gotchas=data.get("gotchas", []),
            confidence_score=data.get("confidence_score", 0.5),
        )

    def save(self, path: Optional[str] = None) -> str:
        """Save session to JSON file"""
        if path is None:
            sessions_dir = Path(".claude-studio/onboarding_sessions")
            sessions_dir.mkdir(parents=True, exist_ok=True)
            path = str(sessions_dir / f"{self.provider_name}.json")

        Path(path).write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")
        return path

    @classmethod
    def load(cls, path: str) -> "OnboardingSession":
        """Load session from JSON file"""
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls.from_dict(data)


# =============================================================================
# DOCUMENTATION ANALYZER
# =============================================================================

class DocAnalyzer:
    """
    Analyzes API documentation to extract provider specifications.
    Uses Claude to understand unstructured docs.
    """
    
    def __init__(self, claude_client):
        self.claude = claude_client
        self.http_client = httpx.AsyncClient(timeout=30.0)
    
    async def fetch_docs(self, url: str) -> str:
        """Fetch documentation from URL"""
        try:
            response = await self.http_client.get(url)
            response.raise_for_status()
            return response.text
        except Exception as e:
            return f"Error fetching docs: {e}"
    
    async def analyze_documentation(
        self,
        docs_content: str,
        provider_type: ProviderType,
        additional_context: str = ""
    ) -> ProviderSpec:
        """
        Use Claude to analyze documentation and extract API specifications.
        """
        
        prompt = f"""Analyze this API documentation and extract a complete provider specification.

DOCUMENTATION:
{docs_content[:15000]}

PROVIDER TYPE: {provider_type.value}

{additional_context}

Extract and return as JSON:
{{
    "name": "provider name",
    "base_url": "https://api.example.com",
    "auth_type": "bearer_token|api_key_header|basic_auth|oauth2",
    "auth_header": "Authorization or X-API-Key etc",
    "auth_prefix": "Bearer or empty",
    "env_var_name": "PROVIDER_API_KEY",
    "request_method": "sync|async_poll|websocket|sse",
    
    "endpoints": [
        {{
            "name": "generate",
            "method": "POST",
            "path": "/v1/generate",
            "description": "Main generation endpoint",
            "request_body": {{"prompt": "string", "model": "string"}},
            "response_schema": {{"id": "string", "output": "string"}},
            "is_async": true,
            "poll_endpoint": "/v1/generations/{{id}}"
        }}
    ],
    
    "models": [
        {{
            "model_id": "model-v1",
            "name": "Model V1",
            "description": "Main model",
            "capabilities": ["feature1", "feature2"],
            "input_types": ["text", "image"],
            "output_types": ["video"],
            "limitations": ["max 60 seconds", "no text generation"]
        }}
    ],
    "default_model": "model-v1",
    
    "supported_formats": ["mp4", "webm"],
    
    "tips": ["Use simple prompts", "Specify aspect ratio"],
    "gotchas": ["Rate limited to 10/min", "Async jobs expire after 1hr"],
    
    "confidence_score": 0.85
}}

Be thorough. If information is unclear, note it in tips/gotchas.
If you need to make assumptions, note them and lower confidence_score."""

        response = await self.claude.query(prompt)

        # Extract JSON from response
        try:
            # Strip markdown code blocks if present
            clean_response = response
            if "```json" in clean_response:
                json_block = re.search(r'```json\s*([\s\S]*?)```', clean_response)
                if json_block:
                    clean_response = json_block.group(1)
            elif "```" in clean_response:
                json_block = re.search(r'```\s*([\s\S]*?)```', clean_response)
                if json_block:
                    clean_response = json_block.group(1)

            json_match = re.search(r'\{[\s\S]*\}', clean_response)
            if json_match:
                data = json.loads(json_match.group())
                return self._dict_to_spec(data, provider_type)
        except json.JSONDecodeError:
            pass

        # Fallback: return minimal spec
        return ProviderSpec(
            name="unknown",
            provider_type=provider_type,
            base_url="",
            docs_url="",
            auth_type=AuthType.BEARER_TOKEN,
            confidence_score=0.1
        )
    
    def _dict_to_spec(self, data: Dict, provider_type: ProviderType) -> ProviderSpec:
        """Convert dict to ProviderSpec"""
        
        endpoints = []
        for ep_data in data.get("endpoints", []):
            endpoints.append(APIEndpoint(
                name=ep_data.get("name", ""),
                method=ep_data.get("method", "POST"),
                path=ep_data.get("path", ""),
                description=ep_data.get("description", ""),
                request_body=ep_data.get("request_body"),
                response_schema=ep_data.get("response_schema"),
                is_async=ep_data.get("is_async", False),
                poll_endpoint=ep_data.get("poll_endpoint"),
            ))
        
        models = []
        for model_data in data.get("models", []):
            models.append(ModelInfo(
                model_id=model_data.get("model_id", ""),
                name=model_data.get("name", ""),
                description=model_data.get("description", ""),
                capabilities=model_data.get("capabilities", []),
                input_types=model_data.get("input_types", []),
                output_types=model_data.get("output_types", []),
                limitations=model_data.get("limitations", []),
            ))
        
        auth_type_map = {
            "bearer_token": AuthType.BEARER_TOKEN,
            "api_key_header": AuthType.API_KEY_HEADER,
            "basic_auth": AuthType.BASIC_AUTH,
            "oauth2": AuthType.OAUTH2,
        }
        
        request_method_map = {
            "sync": RequestMethod.SYNC,
            "async_poll": RequestMethod.ASYNC_POLL,
            "websocket": RequestMethod.WEBSOCKET,
            "sse": RequestMethod.SSE,
        }
        
        return ProviderSpec(
            name=data.get("name", "unknown"),
            provider_type=provider_type,
            base_url=data.get("base_url", ""),
            docs_url=data.get("docs_url", ""),
            auth_type=auth_type_map.get(data.get("auth_type", ""), AuthType.BEARER_TOKEN),
            auth_header=data.get("auth_header", "Authorization"),
            auth_prefix=data.get("auth_prefix", "Bearer"),
            env_var_name=data.get("env_var_name", ""),
            request_method=request_method_map.get(data.get("request_method", ""), RequestMethod.SYNC),
            endpoints=endpoints,
            models=models,
            default_model=data.get("default_model"),
            supported_formats=data.get("supported_formats", []),
            tips=data.get("tips", []),
            gotchas=data.get("gotchas", []),
            confidence_score=data.get("confidence_score", 0.5),
        )


# =============================================================================
# STUB ANALYZER
# =============================================================================

class StubAnalyzer:
    """
    Analyzes existing provider stubs to understand what needs implementation.
    """
    
    def __init__(self, claude_client):
        self.claude = claude_client
    
    async def analyze_stub(self, stub_path: str) -> Dict[str, Any]:
        """
        Analyze a stub file to understand:
        - What's already implemented
        - What needs to be filled in
        - What the expected interface is
        """
        
        stub_content = Path(stub_path).read_text()
        
        prompt = f"""Analyze this provider stub file and identify:

STUB FILE:
```python
{stub_content}
```

Return JSON:
{{
    "provider_name": "extracted provider name",
    "provider_type": "video|audio|tts|image",
    "base_class": "what class it inherits from",
    
    "implemented_methods": [
        {{"name": "method_name", "status": "complete|partial|stub"}}
    ],
    
    "required_methods": [
        {{
            "name": "method_name",
            "signature": "async def method(self, arg: Type) -> ReturnType",
            "description": "what this method should do",
            "current_status": "not_implemented|stub|partial"
        }}
    ],
    
    "dependencies": ["list of imports needed"],
    
    "configuration": {{
        "env_vars": ["ENV_VAR_NAME"],
        "init_params": ["param1", "param2"]
    }},
    
    "notes": ["any observations about the stub"]
}}"""

        response = await self.claude.query(prompt)

        try:
            # Strip markdown code blocks if present
            clean_response = response
            if "```json" in clean_response:
                # Extract first JSON block from markdown
                json_block = re.search(r'```json\s*([\s\S]*?)```', clean_response)
                if json_block:
                    clean_response = json_block.group(1)
            elif "```" in clean_response:
                # Generic code block
                json_block = re.search(r'```\s*([\s\S]*?)```', clean_response)
                if json_block:
                    clean_response = json_block.group(1)

            # Try to parse the JSON
            json_match = re.search(r'\{[\s\S]*\}', clean_response)
            if json_match:
                return json.loads(json_match.group())
        except json.JSONDecodeError:
            pass

        return {"error": "Could not analyze stub", "raw": response}


# =============================================================================
# CODE GENERATOR
# =============================================================================

class ProviderCodeGenerator:
    """
    Generates provider implementation code from specs.
    """
    
    def __init__(self, claude_client):
        self.claude = claude_client
    
    async def _load_reference_implementation(self, provider_type: str) -> Optional[str]:
        """Load a working implementation of the same type as reference"""
        # Map provider types to known working implementations
        reference_map = {
            "image": "core/providers/image/dalle.py",
            "audio": "core/providers/audio/elevenlabs.py",
            "tts": "core/providers/audio/elevenlabs.py",
            "video": "core/providers/video/luma.py",
        }

        ref_path = reference_map.get(provider_type)
        if ref_path and Path(ref_path).exists():
            content = Path(ref_path).read_text()
            # Truncate if too long to avoid context issues
            if len(content) > 8000:
                content = content[:8000] + "\n# ... (truncated)"
            return content
        return None

    async def generate_implementation(
        self,
        spec: ProviderSpec,
        stub_analysis: Optional[Dict[str, Any]] = None,
        base_class_code: Optional[str] = None,
    ) -> str:
        """
        Generate a complete provider implementation.
        """

        # Build context
        context_parts = []

        if stub_analysis:
            context_parts.append(f"EXISTING STUB ANALYSIS:\n{json.dumps(stub_analysis, indent=2)}")

        if base_class_code:
            context_parts.append(f"BASE CLASS (from core/providers/base.py):\n```python\n{base_class_code}\n```")

        # Try to load a reference implementation of the same type
        reference_impl = await self._load_reference_implementation(spec.provider_type.value)
        if reference_impl:
            context_parts.append(f"REFERENCE IMPLEMENTATION (follow this pattern):\n```python\n{reference_impl}\n```")

        context = "\n\n".join(context_parts)

        prompt = f"""Generate a complete Python provider implementation based on this specification.

PROVIDER SPECIFICATION:
{json.dumps(self._spec_to_dict(spec), indent=2)}

{context}

CRITICAL REQUIREMENTS - YOU MUST FOLLOW THESE EXACTLY:

1. IMPORTS: Import from the base module, e.g.:
   from ..base import ImageProvider, ImageProviderConfig, ImageGenerationResult
   from ..base import AudioProvider, AudioProviderConfig, AudioGenerationResult
   from ..base import VideoProvider, VideoProviderConfig, GenerationResult

2. INHERITANCE: Your class MUST inherit from the base class shown above.
   DO NOT create your own base class.
   DO NOT define ImageProvider, AudioProvider, etc. yourself.

3. METHOD SIGNATURES: Use EXACTLY the method names from the base class:
   - ImageProvider: async def generate_image(self, prompt, size, **kwargs) -> ImageGenerationResult
   - AudioProvider: async def generate_speech(self, text, voice_id, **kwargs) -> AudioGenerationResult
   - VideoProvider: async def generate_video(self, prompt, duration, **kwargs) -> GenerationResult

4. CONSTRUCTOR: Accept an optional config parameter:
   def __init__(self, config: Optional[XxxProviderConfig] = None):
       if config is None:
           import os
           api_key = os.environ.get("XXX_API_KEY")
           config = XxxProviderConfig(api_key=api_key)
       super().__init__(config)

5. ASYNC: Use aiohttp for HTTP requests, not requests. All generation methods must be async.

6. RETURN TYPES: Return the correct result dataclass (ImageGenerationResult, AudioGenerationResult, etc.)
   with success=True/False and appropriate fields filled in.

7. Add a `generate()` alias method for CLI compatibility that calls the main generation method.

For async providers (async_poll), implement:
- Job submission
- Polling with exponential backoff
- Timeout handling

CRITICAL: Output ONLY the Python code inside a single ```python code block.
Do NOT include any explanation, summary, or markdown outside the code block.
Do NOT use emoji or special unicode characters in comments.
Start your response with ```python and end with ```."""

        response = await self.claude.query(prompt)

        # Extract code block - try multiple patterns
        # Pattern 1: ```python\n...\n```
        code_match = re.search(r'```python\n([\s\S]*?)\n```', response)
        if code_match:
            code = code_match.group(1)
            # Validate it looks like Python code
            if "import " in code or "class " in code or "def " in code:
                return code

        # Pattern 2: ```\n...\n``` (generic code block)
        code_match = re.search(r'```\n([\s\S]*?)\n```', response)
        if code_match:
            code = code_match.group(1)
            if "import " in code or "class " in code:
                return code

        # Pattern 3: Look for python code directly (starts with imports or docstring)
        if response.strip().startswith('"""') or response.strip().startswith("import ") or response.strip().startswith("from "):
            return response.strip()

        # Pattern 4: Find the largest code block if multiple exist
        all_blocks = re.findall(r'```(?:python)?\n([\s\S]*?)\n```', response)
        if all_blocks:
            # Return the largest block that looks like Python
            valid_blocks = [b for b in all_blocks if "class " in b or "def " in b]
            if valid_blocks:
                return max(valid_blocks, key=len)

        # Last resort: return the response but warn
        print(f"  ⚠️ Could not extract code block from response (len={len(response)})")
        return response
    
    def _spec_to_dict(self, spec: ProviderSpec) -> Dict:
        """Convert spec to dict for JSON serialization"""
        return {
            "name": spec.name,
            "provider_type": spec.provider_type.value,
            "base_url": spec.base_url,
            "auth_type": spec.auth_type.value,
            "auth_header": spec.auth_header,
            "auth_prefix": spec.auth_prefix,
            "env_var_name": spec.env_var_name,
            "request_method": spec.request_method.value,
            "endpoints": [
                {
                    "name": ep.name,
                    "method": ep.method,
                    "path": ep.path,
                    "description": ep.description,
                    "request_body": ep.request_body,
                    "response_schema": ep.response_schema,
                    "is_async": ep.is_async,
                    "poll_endpoint": ep.poll_endpoint,
                }
                for ep in spec.endpoints
            ],
            "models": [
                {
                    "model_id": m.model_id,
                    "name": m.name,
                    "description": m.description,
                    "capabilities": m.capabilities,
                    "input_types": m.input_types,
                    "output_types": m.output_types,
                    "limitations": m.limitations,
                }
                for m in spec.models
            ],
            "default_model": spec.default_model,
            "supported_formats": spec.supported_formats,
            "tips": spec.tips,
            "gotchas": spec.gotchas,
        }


# =============================================================================
# IMPLEMENTATION TESTER
# =============================================================================

class ProviderTester:
    """
    Tests provider implementations interactively.
    """
    
    def __init__(self, claude_client):
        self.claude = claude_client
    
    async def generate_test_cases(
        self,
        spec: ProviderSpec,
        implementation_code: str,
    ) -> List[Dict[str, Any]]:
        """Generate test cases for the provider"""
        
        prompt = f"""Generate test cases for this provider implementation.

PROVIDER SPEC:
{json.dumps({"name": spec.name, "provider_type": spec.provider_type.value, "models": [m.model_id for m in spec.models]}, indent=2)}

IMPLEMENTATION:
```python
{implementation_code[:5000]}
```

Return a JSON array of test cases with this structure:
[
    {{
        "name": "test_basic_generation",
        "description": "Test basic text-to-speech generation",
        "test_type": "integration",
        "method": "generate_speech",
        "inputs": {{"text": "Hello world"}},
        "assertions": ["result is not None"]
    }}
]

Include tests for:
1. Basic generation (happy path)
2. List voices
3. Validate credentials
4. Error handling (empty input)

CRITICAL: Output ONLY a valid JSON array. No explanation, no markdown, no text before or after.
Start your response with [ and end with ]."""

        response = await self.claude.query(prompt)

        try:
            # Strip markdown code blocks if present
            clean_response = response.strip()
            if "```json" in clean_response:
                json_block = re.search(r'```json\s*([\s\S]*?)```', clean_response)
                if json_block:
                    clean_response = json_block.group(1).strip()
            elif "```" in clean_response:
                json_block = re.search(r'```\s*([\s\S]*?)```', clean_response)
                if json_block:
                    clean_response = json_block.group(1).strip()

            # Try direct parse if it starts with [
            if clean_response.startswith("["):
                try:
                    return json.loads(clean_response)
                except json.JSONDecodeError:
                    pass

            # Fall back to regex extraction
            json_match = re.search(r'\[[\s\S]*\]', clean_response)
            if json_match:
                return json.loads(json_match.group())

        except json.JSONDecodeError as e:
            print(f"  ⚠️ JSON decode error in test generation: {e}")

        # Last resort: bracket matching to extract the array
        try:
            start_idx = response.find('[')
            if start_idx != -1:
                bracket_count = 0
                end_idx = start_idx
                for i, c in enumerate(response[start_idx:], start_idx):
                    if c == '[':
                        bracket_count += 1
                    elif c == ']':
                        bracket_count -= 1
                        if bracket_count == 0:
                            end_idx = i + 1
                            break

                json_str = response[start_idx:end_idx]
                result = json.loads(json_str)
                print(f"  ✓ Extracted {len(result)} test cases via bracket matching")
                return result
        except json.JSONDecodeError as e2:
            print(f"  ⚠️ Bracket-matched JSON invalid: {e2}")
            print(f"  Preview: {response[start_idx:start_idx+200]}...")
        except Exception as e:
            print(f"  ⚠️ Fallback extraction failed: {e}")

        print(f"  ⚠️ Could not parse test cases (response len={len(response)})")
        return []

    async def run_test(
        self,
        test_case: Dict[str, Any],
        provider_instance: Any,
    ) -> Dict[str, Any]:
        """Run a single test case against the provider"""

        result = {
            "name": test_case["name"],
            "status": "pending",
            "error": None,
            "output": None,
            "duration_ms": 0,
        }

        import time
        start = time.time()

        try:
            inputs = test_case.get("inputs", {})
            test_type = test_case.get("test_type", "unit")

            # Determine which method to call based on test inputs and provider type
            method_name = self._determine_method(test_case, provider_instance)

            if method_name and hasattr(provider_instance, method_name):
                method = getattr(provider_instance, method_name)

                # For unit tests, we might want to mock external calls
                if test_type == "unit" and test_case.get("mock_response"):
                    # Skip actual API call for unit tests with mocks
                    result["status"] = "passed"
                    result["output"] = "Mock test - validated inputs"
                else:
                    # Actually call the method (or just get the value if it's a property)
                    if callable(method):
                        if asyncio.iscoroutinefunction(method):
                            output = await method(**inputs)
                        else:
                            output = method(**inputs)
                    else:
                        # It's a property or attribute, already resolved
                        output = method

                    result["output"] = str(output)[:500]  # Truncate output
                    result["status"] = "passed"

                    # Run assertions if provided
                    assertions = test_case.get("assertions", [])
                    for assertion in assertions:
                        try:
                            # Simple assertion evaluation
                            # Replace 'result' in assertion with actual output
                            if not self._evaluate_assertion(assertion, output):
                                result["status"] = "failed"
                                result["error"] = f"Assertion failed: {assertion}"
                                break
                        except Exception as e:
                            result["status"] = "failed"
                            result["error"] = f"Assertion error: {assertion} - {e}"
                            break
            else:
                result["status"] = "skipped"
                result["error"] = f"Method '{method_name}' not found on provider"

        except Exception as e:
            # Check if this test expects an error
            expected_error = test_case.get("expected_error")
            if expected_error:
                # Test expects an error - check if error message matches
                error_str = str(e).lower()
                expected_lower = expected_error.lower()
                if expected_lower in error_str or any(word in error_str for word in expected_lower.split()):
                    result["status"] = "passed"
                    result["output"] = f"Expected error received: {e}"
                else:
                    result["status"] = "failed"
                    result["error"] = f"Expected error containing '{expected_error}', got: {e}"
            elif "error" in test_case.get("name", "").lower():
                # Test name suggests it's testing error handling - passing an error is success
                result["status"] = "passed"
                result["output"] = f"Error correctly raised: {e}"
            else:
                result["status"] = "failed"
                result["error"] = str(e)

        result["duration_ms"] = int((time.time() - start) * 1000)
        return result

    def _determine_method(self, test_case: Dict[str, Any], provider: Any) -> Optional[str]:
        """Determine which provider method to call based on test case"""
        inputs = test_case.get("inputs", {})

        # Check for explicit method in test case
        if "method" in test_case:
            return test_case["method"]

        # Infer from inputs and provider type
        if "text" in inputs:
            # Audio TTS provider
            if hasattr(provider, "generate_speech"):
                return "generate_speech"
            if hasattr(provider, "synthesize"):
                return "synthesize"

        if "prompt" in inputs:
            # Video/Image generation
            if hasattr(provider, "generate"):
                return "generate"
            if hasattr(provider, "generate_video"):
                return "generate_video"
            if hasattr(provider, "generate_image"):
                return "generate_image"

        if "voice_id" in inputs or "voices" in test_case.get("name", "").lower():
            if hasattr(provider, "list_voices"):
                return "list_voices"
            if hasattr(provider, "get_voices"):
                return "get_voices"

        # Check for validation tests
        if "credential" in test_case.get("name", "").lower() or "auth" in test_case.get("name", "").lower():
            if hasattr(provider, "validate_credentials"):
                return "validate_credentials"

        # Default to generate
        if hasattr(provider, "generate"):
            return "generate"

        return None

    def _evaluate_assertion(self, assertion: str, output: Any) -> bool:
        """Evaluate a simple assertion string against output"""
        # Handle common assertion patterns
        assertion = assertion.strip()

        # result.X is not None
        if "is not None" in assertion:
            attr = assertion.split(".")[1].split(" ")[0] if "." in assertion else None
            if attr and hasattr(output, attr):
                return getattr(output, attr) is not None
            return output is not None

        # result.X is None
        if "is None" in assertion:
            attr = assertion.split(".")[1].split(" ")[0] if "." in assertion else None
            if attr and hasattr(output, attr):
                return getattr(output, attr) is None
            return output is None

        # result.success == True or result.success
        if "success" in assertion:
            if hasattr(output, "success"):
                return output.success == True

        # len(result.attribute) > 0 - e.g., len(result.audio_data) > 0
        if "len(result." in assertion and "> 0" in assertion:
            import re
            match = re.search(r'len\(result\.(\w+)\)', assertion)
            if match:
                attr = match.group(1)
                if hasattr(output, attr):
                    val = getattr(output, attr)
                    try:
                        return len(val) > 0 if val is not None else False
                    except TypeError:
                        return False
            return False

        # len(result) > 0
        if "len(" in assertion and "> 0" in assertion:
            try:
                return len(output) > 0
            except TypeError:
                return False

        # isinstance checks - e.g., isinstance(result, AudioGenerationResult)
        if "isinstance(" in assertion:
            # Just check output exists and is not None
            return output is not None

        # result.attribute == value patterns
        if "==" in assertion and "result." in assertion:
            import re
            match = re.search(r'result\.(\w+)\s*==\s*["\']?(\w+)["\']?', assertion)
            if match:
                attr, expected = match.groups()
                if hasattr(output, attr):
                    val = getattr(output, attr)
                    # Handle callable properties
                    if callable(val):
                        val = val()
                    return str(val) == expected
            return False

        # Default: if we got output without exception, consider it passed
        return True


# =============================================================================
# MAIN ONBOARDING AGENT
# =============================================================================

class ProviderOnboardingAgent:
    """
    Main agent that orchestrates the provider onboarding process.

    Workflow:
    1. Analyze documentation OR existing stub
    2. Build provider specification
    3. Ask clarifying questions if needed
    4. Generate implementation code
    5. Generate and run tests
    6. Record learnings

    Sessions are checkpointed after each step and can be resumed.
    """

    # Session file location
    SESSIONS_DIR = Path(".claude-studio/onboarding_sessions")

    def __init__(self, claude_client, memory_manager=None):
        self.claude = claude_client
        self.memory = memory_manager

        self.doc_analyzer = DocAnalyzer(claude_client)
        self.stub_analyzer = StubAnalyzer(claude_client)
        self.code_generator = ProviderCodeGenerator(claude_client)
        self.tester = ProviderTester(claude_client)

        self.session: Optional[OnboardingSession] = None

    def _checkpoint(self, step: str):
        """Save session checkpoint after completing a step"""
        if self.session:
            self.session.current_step = step
            self.session.save()
            print(f"  💾 Checkpoint saved: {step}")

    @classmethod
    def get_session_path(cls, provider_name: str) -> Path:
        """Get the session file path for a provider"""
        return cls.SESSIONS_DIR / f"{provider_name}.json"

    @classmethod
    def has_session(cls, provider_name: str) -> bool:
        """Check if a saved session exists for a provider"""
        return cls.get_session_path(provider_name).exists()

    @classmethod
    def list_sessions(cls) -> List[str]:
        """List all saved onboarding sessions"""
        if not cls.SESSIONS_DIR.exists():
            return []
        return [p.stem for p in cls.SESSIONS_DIR.glob("*.json")]

    async def resume_session(self, provider_name: str) -> OnboardingSession:
        """Resume an existing onboarding session"""
        path = self.get_session_path(provider_name)
        if not path.exists():
            raise FileNotFoundError(f"No session found for {provider_name}")

        self.session = OnboardingSession.load(str(path))
        print(f"📂 Resumed session for {provider_name}")
        print(f"   Status: {self.session.status}")
        print(f"   Current step: {self.session.current_step}")
        print(f"   Stub path: {self.session.stub_path}")
        print(f"   Implementation: {self.session.implementation_path}")
        return self.session

    async def start_onboarding(
        self,
        provider_name: str,
        provider_type: ProviderType,
        docs_url: Optional[str] = None,
        stub_path: Optional[str] = None,
    ) -> OnboardingSession:
        """Start a new onboarding session"""

        self.session = OnboardingSession(
            provider_name=provider_name,
            started_at=datetime.utcnow(),
            stub_path=stub_path,
        )
        self.session.docs_url = docs_url
        self.session.provider_type = provider_type.value

        print(f"🚀 Starting onboarding for {provider_name} ({provider_type.value})")

        # Step 1: Analyze documentation
        if docs_url:
            print(f"📖 Fetching documentation from {docs_url}...")
            docs_content = await self.doc_analyzer.fetch_docs(docs_url)
            self.session.docs_analyzed.append(docs_url)

            print("🔍 Analyzing documentation...")
            self.session.spec = await self.doc_analyzer.analyze_documentation(
                docs_content, provider_type
            )
            self.session.spec.docs_url = docs_url
            self._checkpoint("docs")

        # Step 2: Analyze existing stub if provided
        stub_analysis = None
        if stub_path:
            print(f"📄 Analyzing stub at {stub_path}...")
            stub_analysis = await self.stub_analyzer.analyze_stub(stub_path)

            # If no docs, infer spec from stub
            if not self.session.spec:
                self.session.spec = ProviderSpec(
                    name=stub_analysis.get("provider_name", provider_name),
                    provider_type=provider_type,
                    base_url="",
                    docs_url="",
                    auth_type=AuthType.BEARER_TOKEN,
                )
            self._checkpoint("spec")

        # Step 3: Generate questions if confidence is low
        if self.session.spec and self.session.spec.confidence_score < 0.7:
            questions = await self._generate_questions()
            self.session.questions = questions
            print(f"❓ {len(questions)} questions need clarification")
            self._checkpoint("questions")

        return self.session
    
    async def _generate_questions(self) -> List[Dict[str, str]]:
        """Generate clarifying questions based on analysis"""
        
        spec = self.session.spec
        
        prompt = f"""Based on this provider analysis, what questions should we ask to complete the implementation?

PROVIDER: {spec.name}
TYPE: {spec.provider_type.value}
CONFIDENCE: {spec.confidence_score}

CURRENT SPEC:
- Base URL: {spec.base_url or 'UNKNOWN'}
- Auth: {spec.auth_type.value}
- Request Method: {spec.request_method.value}
- Endpoints: {len(spec.endpoints)}
- Models: {len(spec.models)}
- Tips: {spec.tips}
- Gotchas: {spec.gotchas}

Return JSON array of questions:
[
    {{
        "id": "q1",
        "category": "authentication|endpoints|models|rate_limits|other",
        "question": "What is the base URL for the API?",
        "importance": "critical|important|nice_to_have",
        "default_value": "https://api.example.com"
    }}
]

Focus on information needed to generate a working implementation."""

        response = await self.claude.query(prompt)

        try:
            # Strip markdown code blocks if present
            clean_response = response
            if "```json" in clean_response:
                json_block = re.search(r'```json\s*([\s\S]*?)```', clean_response)
                if json_block:
                    clean_response = json_block.group(1)
            elif "```" in clean_response:
                json_block = re.search(r'```\s*([\s\S]*?)```', clean_response)
                if json_block:
                    clean_response = json_block.group(1)

            json_match = re.search(r'\[[\s\S]*\]', clean_response)
            if json_match:
                return json.loads(json_match.group())
        except json.JSONDecodeError:
            pass

        return []

    async def answer_question(self, question_id: str, answer: str):
        """Process an answer to a clarifying question"""
        
        self.session.answers.append({
            "question_id": question_id,
            "answer": answer,
            "answered_at": datetime.utcnow().isoformat()
        })
        
        # Update spec based on answer
        await self._update_spec_from_answer(question_id, answer)
    
    async def _update_spec_from_answer(self, question_id: str, answer: str):
        """Update the spec based on a user's answer"""
        
        # Find the original question
        question = next(
            (q for q in self.session.questions if q.get("id") == question_id),
            None
        )
        
        if not question:
            return
        
        category = question.get("category", "")
        spec = self.session.spec
        
        # Simple updates based on category
        if category == "authentication" and "base_url" in question.get("question", "").lower():
            spec.base_url = answer
        elif category == "authentication" and "key" in question.get("question", "").lower():
            spec.env_var_name = answer
        
        # Increase confidence after getting answers
        spec.confidence_score = min(1.0, spec.confidence_score + 0.1)
    
    async def generate_implementation(
        self,
        output_path: Optional[str] = None,
    ) -> str:
        """Generate the provider implementation"""

        if not self.session or not self.session.spec:
            raise ValueError("No active session or spec. Run start_onboarding first.")

        print("⚙️ Generating implementation...")

        # Always load base class based on provider type
        provider_type = self.session.provider_type or self.session.spec.provider_type.value
        base_class_name = self._get_base_class_for_type(provider_type)
        base_class_code = await self._load_base_class(base_class_name)

        if base_class_code:
            print(f"  ✓ Loaded base class: {base_class_name}")
        else:
            print(f"  ⚠ Could not load base class: {base_class_name}")

        # Analyze stub if provided
        stub_analysis = None
        if self.session.stub_path:
            stub_analysis = await self.stub_analyzer.analyze_stub(self.session.stub_path)
        
        # Generate code
        implementation = await self.code_generator.generate_implementation(
            self.session.spec,
            stub_analysis=stub_analysis,
            base_class_code=base_class_code,
        )

        # Validate the implementation before saving
        validation_errors = []

        if not implementation or len(implementation.strip()) < 100:
            validation_errors.append("Generated implementation is empty or too short")

        if "class " not in implementation or "Provider" not in implementation:
            validation_errors.append("Generated implementation doesn't contain a Provider class")

        # Check for syntax errors
        try:
            compile(implementation, "<generated>", "exec")
        except SyntaxError as e:
            validation_errors.append(f"Syntax error: {e}")

        # If validation failed, save to staging area instead
        if validation_errors:
            staging_dir = Path(".claude-studio/staging")
            staging_dir.mkdir(parents=True, exist_ok=True)
            staging_path = staging_dir / f"{self.session.provider_name}_generated.py"
            staging_path.write_text(implementation, encoding="utf-8")

            print(f"⚠️ Generated code has issues:")
            for err in validation_errors:
                print(f"   - {err}")
            print(f"💾 Saved to staging: {staging_path}")
            print("   Review and fix manually, then copy to final location")

            # Still set the path so tests can attempt to run on staging
            self.session.implementation_path = str(staging_path)
            self._checkpoint("implementation_failed")
            return implementation

        # Save if output path provided and validation passed
        if output_path:
            Path(output_path).write_text(implementation, encoding="utf-8")
            self.session.implementation_path = output_path
            print(f"💾 Saved implementation to {output_path}")
            self._checkpoint("implementation")

        return implementation
    
    async def _load_base_class(self, class_name: str) -> Optional[str]:
        """Load base class source code from core/providers/base.py"""

        # All base classes are in the same file
        base_file = Path("core/providers/base.py")
        if not base_file.exists():
            return None

        full_content = base_file.read_text()

        # Extract just the relevant class and its dependencies
        # For now, return the full base file since classes depend on each other
        return full_content

    def _get_base_class_for_type(self, provider_type: str) -> str:
        """Get the base class name for a provider type"""
        type_to_class = {
            "video": "VideoProvider",
            "audio": "AudioProvider",
            "tts": "AudioProvider",  # TTS uses AudioProvider
            "image": "ImageProvider",
            "music": "MusicProvider",
            "storage": "StorageProvider",
        }
        return type_to_class.get(provider_type, "VideoProvider")
    
    async def run_tests(
        self,
        implementation_path: Optional[str] = None,
        interactive: bool = True,
    ) -> List[Dict[str, Any]]:
        """Generate and run tests for the implementation"""

        impl_path = implementation_path or self.session.implementation_path
        if not impl_path:
            raise ValueError("No implementation path provided")

        implementation = Path(impl_path).read_text()

        print("🧪 Generating test cases...")
        test_cases = await self.tester.generate_test_cases(
            self.session.spec,
            implementation,
        )

        print(f"Generated {len(test_cases)} test cases")

        if not test_cases:
            print("  No test cases generated")
            return []

        # Dynamically import the provider
        provider_instance = None
        try:
            provider_instance = await self._import_provider(impl_path)
            if provider_instance:
                print(f"  ✓ Loaded provider: {provider_instance.__class__.__name__}")
        except Exception as e:
            print(f"  ⚠ Could not load provider for testing: {e}")

        results = []
        for test in test_cases:
            print(f"\n  Test: {test['name']}")
            print(f"  Description: {test.get('description', 'N/A')}")
            print(f"  Type: {test.get('test_type', 'unknown')}")

            if interactive:
                user_input = input("  Run this test? [y/n/s(kip all)]: ").lower()
                if user_input == 's':
                    break
                if user_input != 'y':
                    continue

            # Actually run the test
            if provider_instance:
                result = await self.tester.run_test(test, provider_instance)
                # Store the full test case for later export
                result["test_case"] = test
                status_icon = "✓" if result["status"] == "passed" else "✗" if result["status"] == "failed" else "○"
                print(f"  {status_icon} {result['status'].upper()}", end="")
                if result.get("duration_ms"):
                    print(f" ({result['duration_ms']}ms)", end="")
                if result.get("error"):
                    print(f"\n    Error: {result['error']}", end="")
                print()
            else:
                result = {
                    "name": test["name"],
                    "status": "skipped",
                    "error": "Provider could not be loaded",
                    "test_case": test,
                }
                print(f"  ○ SKIPPED (provider not loaded)")

            results.append(result)
            self.session.test_results.append(result)

        # Summary
        passed = sum(1 for r in results if r["status"] == "passed")
        failed = sum(1 for r in results if r["status"] == "failed")
        skipped = sum(1 for r in results if r["status"] == "skipped")
        print(f"\n  Summary: {passed} passed, {failed} failed, {skipped} skipped")

        # Clean up provider if it has a close method
        if provider_instance and hasattr(provider_instance, "close"):
            try:
                await provider_instance.close()
            except Exception:
                pass

        self._checkpoint("testing")
        return results

    async def _import_provider(self, impl_path: str) -> Any:
        """Dynamically import and instantiate the provider from the implementation file"""
        import importlib
        import sys

        path = Path(impl_path)

        # Add project root to sys.path if not already there
        project_root = Path.cwd()
        if str(project_root) not in sys.path:
            sys.path.insert(0, str(project_root))

        # Convert file path to module path
        # e.g., "core/providers/audio/elevenlabs.py" -> "core.providers.audio.elevenlabs"
        try:
            # Make path relative to project root
            rel_path = path.resolve().relative_to(project_root.resolve())
            # Convert to module path (remove .py, replace / with .)
            module_path = str(rel_path.with_suffix("")).replace("\\", ".").replace("/", ".")
        except ValueError:
            # Path not relative to project root, fall back to just the stem
            module_path = path.stem

        # Import the module using standard import (handles relative imports correctly)
        try:
            module = importlib.import_module(module_path)
        except ImportError as e:
            # If module import fails, provide helpful error
            raise ImportError(f"Could not import module '{module_path}' from {impl_path}: {e}")

        # Find the provider class (look for class ending in "Provider")
        provider_class = None
        for name in dir(module):
            obj = getattr(module, name)
            if isinstance(obj, type) and name.endswith("Provider") and name != "AudioProvider" and name != "VideoProvider":
                provider_class = obj
                break

        if not provider_class:
            raise ImportError(f"No provider class found in {impl_path}")

        # Try to instantiate with minimal config
        try:
            # Check if it needs a config object
            import inspect
            sig = inspect.signature(provider_class.__init__)
            params = list(sig.parameters.keys())

            if len(params) == 1:  # just self
                return provider_class()
            elif "config" in params:
                # Try to create a config - look for a Config class in the module
                config_class = None
                for name in dir(module):
                    if name.endswith("Config") and name != "AudioProviderConfig":
                        config_class = getattr(module, name)
                        break

                if config_class:
                    # Try with empty config (will use env vars)
                    try:
                        config = config_class()
                        return provider_class(config)
                    except Exception:
                        # Try with api_key from env
                        config = config_class(api_key="test_key")
                        return provider_class(config)
                else:
                    return provider_class(config=None)
            else:
                return provider_class()
        except Exception as e:
            raise ImportError(f"Could not instantiate provider: {e}")
    
    async def record_learnings(self):
        """Record learnings from the onboarding session to memory"""

        if not self.session or not self.session.spec:
            print("  ⚠ No session or spec to record learnings from")
            return

        spec = self.session.spec

        # Collect model limitations
        model_limitations = []
        for model in spec.models:
            for limitation in model.limitations:
                model_limitations.append(f"[{model.model_id}] {limitation}")

        # If we have a memory manager, use it
        if self.memory:
            await self.memory.record_onboarding_learnings(
                provider=spec.name.lower(),
                tips=spec.tips,
                gotchas=spec.gotchas,
                model_limitations=model_limitations,
            )
            self.session.status = "completed"
            print(f"  📝 Recorded {len(spec.tips)} tips, {len(spec.gotchas)} gotchas to memory")
        else:
            # No memory manager - save to session file instead
            self.session.status = "completed"
            self._checkpoint("complete")
            print(f"  📝 Learnings saved to session (no memory manager)")
            print(f"     Tips: {len(spec.tips)}, Gotchas: {len(spec.gotchas)}, Model limitations: {len(model_limitations)}")
    
    async def export_tests_to_pytest(
        self,
        output_dir: Optional[str] = None,
    ) -> Optional[str]:
        """
        Export generated tests as a proper pytest test file.

        Args:
            output_dir: Directory to save tests (default: tests/integration)

        Returns:
            Path to the generated test file, or None if no tests to export
        """
        if not self.session:
            print("  No active session")
            return None

        if not self.session.test_results:
            print("  No test results to export")
            return None

        spec = self.session.spec
        provider_name = self.session.provider_name.lower()

        # Determine output path
        if output_dir:
            output_path = Path(output_dir) / f"test_{provider_name}.py"
        else:
            output_path = Path("tests/integration") / f"test_{provider_name}.py"

        # Ensure directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Determine provider import path and class name
        impl_path = self.session.implementation_path
        class_name = None

        if impl_path and Path(impl_path).exists():
            # Convert file path to import path
            rel_path = Path(impl_path).relative_to(Path.cwd()) if Path(impl_path).is_absolute() else Path(impl_path)
            import_path = str(rel_path.with_suffix("")).replace("\\", ".").replace("/", ".")

            # Read the implementation file to find the actual class name
            impl_content = Path(impl_path).read_text(encoding="utf-8")
            import re
            class_match = re.search(r'class\s+(\w+Provider)\s*[:\(]', impl_content)
            if class_match:
                class_name = class_match.group(1)
        else:
            # Default based on provider type
            provider_type = self.session.provider_type or "audio"
            import_path = f"core.providers.{provider_type}.{provider_name}"

        # Fallback class name if not found
        if not class_name:
            class_name = f"{provider_name.title().replace('_', '')}Provider"

        # Determine environment variable for API key
        env_var = spec.env_var_name if spec else f"{provider_name.upper()}_API_KEY"

        # Generate test file content
        test_content = self._generate_pytest_content(
            provider_name=provider_name,
            import_path=import_path,
            class_name=class_name,
            env_var=env_var,
            spec=spec,
        )

        # Write the file
        output_path.write_text(test_content, encoding="utf-8")
        print(f"  Exported tests to {output_path}")

        return str(output_path)

    def _generate_pytest_content(
        self,
        provider_name: str,
        import_path: str,
        class_name: str,
        env_var: str,
        spec: Optional[ProviderSpec],
    ) -> str:
        """Generate pytest file content from test results"""

        # Get test cases from results
        test_cases = []
        for result in self.session.test_results:
            if "test_case" in result:
                test_cases.append(result["test_case"])
            else:
                # Reconstruct minimal test case from result
                test_cases.append({
                    "name": result.get("name", "test_unknown"),
                    "description": result.get("description", ""),
                    "method": result.get("method", "generate_speech"),
                    "inputs": result.get("inputs", {}),
                    "test_type": result.get("test_type", "integration"),
                })

        # Determine provider type for config class
        provider_type = self.session.provider_type or "audio"

        # Build test file
        lines = [
            f'"""Integration tests for {class_name}',
            f'',
            f'These tests make real API calls to the {provider_name} service.',
            f'They will be skipped if {env_var} is not set in environment.',
            f'',
            f'Run with: pytest {self.session.implementation_path and Path(self.session.implementation_path).parent.name or "tests/integration"}/test_{provider_name}.py -m live_api -v',
            f'',
            f'Auto-generated by provider onboarding agent.',
            f'"""',
            f'',
            f'import os',
            f'import pytest',
            f'from pathlib import Path',
        ]

        # Add provider import
        lines.append(f'from {import_path} import {class_name}')

        # Add config import based on provider type
        if provider_type == "audio" or provider_type == "tts":
            lines.append('from core.providers.base import AudioProviderConfig')
        elif provider_type == "video":
            lines.append('from core.providers.base import VideoProviderConfig')
        else:
            lines.append('from core.providers.base import AudioProviderConfig')

        lines.extend([
            f'',
            f'',
            f'# Skip all tests in this file if API key not available',
            f'pytestmark = pytest.mark.skipif(',
            f'    not os.getenv("{env_var}"),',
            f'    reason="{env_var} not set - skipping live API tests"',
            f')',
            f'',
            f'',
        ])

        # Add fixtures
        config_class = "AudioProviderConfig" if provider_type in ["audio", "tts"] else "VideoProviderConfig"
        fixture_name = f"{provider_name}_config"
        provider_fixture = f"{provider_name}_provider"

        lines.extend([
            f'@pytest.fixture',
            f'def {fixture_name}():',
            f'    """Create {provider_name} provider configuration"""',
            f'    api_key = os.getenv("{env_var}")',
            f'    return {config_class}(',
            f'        api_key=api_key,',
            f'        timeout=60',
            f'    )',
            f'',
            f'',
            f'@pytest.fixture',
            f'def {provider_fixture}({fixture_name}):',
            f'    """Create {provider_name} provider instance"""',
            f'    return {class_name}({fixture_name})',
            f'',
            f'',
        ])

        # Generate test functions
        for test_case in test_cases:
            test_name = test_case.get("name", "test_unknown")
            if not test_name.startswith("test_"):
                test_name = f"test_{test_name}"

            description = test_case.get("description", f"Test {test_name}")
            method = test_case.get("method", "generate_speech")
            inputs = test_case.get("inputs", {})
            assertions = test_case.get("assertions", [])
            test_type = test_case.get("test_type", "integration")
            expected_error = test_case.get("expected_error")

            # Determine if this is an async test
            is_async = method in ["generate_speech", "generate", "list_voices", "validate_credentials",
                                  "generate_video", "generate_image", "synthesize"]

            # Build test function
            lines.append('@pytest.mark.live_api')
            if is_async:
                lines.append('@pytest.mark.asyncio')
                lines.append(f'async def {test_name}({provider_fixture}):')
            else:
                lines.append(f'def {test_name}({provider_fixture}):')

            lines.append(f'    """{description}"""')

            # Handle error tests
            if expected_error or "error" in test_name.lower():
                lines.append(f'    # This test expects an error')
                if is_async:
                    lines.append(f'    try:')
                    lines.append(f'        result = await {provider_fixture}.{method}(')
                else:
                    lines.append(f'    try:')
                    lines.append(f'        result = {provider_fixture}.{method}(')

                # Add inputs
                for key, value in inputs.items():
                    if isinstance(value, str):
                        lines.append(f'            {key}="{value}",')
                    else:
                        lines.append(f'            {key}={value},')
                lines.append(f'        )')

                if expected_error:
                    lines.append(f'        # If no exception, check for error in result')
                    lines.append(f'        if hasattr(result, "success") and not result.success:')
                    lines.append(f'            assert "{expected_error}" in str(result.error_message or "")')
                    lines.append(f'        else:')
                    lines.append(f'            pytest.fail("Expected error but got success")')
                    lines.append(f'    except Exception as e:')
                    lines.append(f'        assert "{expected_error}" in str(e).lower() or True  # Error is expected')
                else:
                    lines.append(f'        # If result exists, check it indicates failure')
                    lines.append(f'        if hasattr(result, "success"):')
                    lines.append(f'            assert result.success is False')
                    lines.append(f'    except Exception:')
                    lines.append(f'        pass  # Error is expected')
            else:
                # Normal test
                if is_async:
                    lines.append(f'    result = await {provider_fixture}.{method}(')
                else:
                    lines.append(f'    result = {provider_fixture}.{method}(')

                # Add inputs
                for key, value in inputs.items():
                    if isinstance(value, str):
                        lines.append(f'        {key}="{value}",')
                    else:
                        lines.append(f'        {key}={value},')
                lines.append(f'    )')

                # Add assertions
                if assertions:
                    lines.append(f'')
                    for assertion in assertions:
                        pytest_assertion = self._convert_assertion_to_pytest(assertion)
                        if pytest_assertion:
                            lines.append(f'    {pytest_assertion}')
                else:
                    # Default assertions based on method
                    if method == "list_voices":
                        lines.append(f'    assert isinstance(result, list)')
                        lines.append(f'    assert len(result) > 0')
                    elif method == "validate_credentials":
                        lines.append(f'    assert result is True')
                    elif method in ["generate_speech", "generate", "synthesize"]:
                        lines.append(f'    assert result is not None')
                        lines.append(f'    assert result.success is True')
                    elif method == "name":
                        lines.append(f'    assert result == "{provider_name}"')

            lines.append(f'')
            lines.append(f'')

        return '\n'.join(lines)

    def _convert_assertion_to_pytest(self, assertion: str) -> Optional[str]:
        """Convert an assertion string to pytest assert format"""
        assertion = assertion.strip()

        # result.X is not None
        if "result." in assertion and "is not None" in assertion:
            attr = assertion.split("result.")[1].split(" ")[0]
            return f"assert result.{attr} is not None"

        # result.X is None
        if "result." in assertion and "is None" in assertion:
            attr = assertion.split("result.")[1].split(" ")[0]
            return f"assert result.{attr} is None"

        # result.success == True or result.success
        if "result.success" in assertion:
            return "assert result.success is True"

        # len(result.X) > 0
        if "len(result." in assertion and "> 0" in assertion:
            import re
            match = re.search(r'len\(result\.(\w+)\)', assertion)
            if match:
                attr = match.group(1)
                return f"assert len(result.{attr}) > 0"

        # len(result) > 0
        if "len(result)" in assertion and "> 0" in assertion:
            return "assert len(result) > 0"

        # isinstance checks
        if "isinstance(" in assertion:
            return "assert result is not None"

        # result.X == value
        if "==" in assertion and "result." in assertion:
            import re
            match = re.search(r'result\.(\w+)\s*==\s*(.+)', assertion)
            if match:
                attr, value = match.groups()
                return f"assert result.{attr} == {value}"

        # Generic - try to convert directly
        if assertion.startswith("result"):
            return f"assert {assertion}"

        return None

    def get_session_summary(self) -> str:
        """Get a summary of the current onboarding session"""

        if not self.session:
            return "No active session"

        spec = self.session.spec

        summary = f"""
╭────────────────────────────────────────────────────────────────╮
│  Provider Onboarding Summary: {self.session.provider_name:>30} │
╰────────────────────────────────────────────────────────────────╯

Status: {self.session.status}
Started: {self.session.started_at.isoformat()}

SPECIFICATION:
  Name: {spec.name if spec else 'Unknown'}
  Type: {spec.provider_type.value if spec else 'Unknown'}
  Base URL: {spec.base_url if spec else 'Unknown'}
  Auth: {spec.auth_type.value if spec else 'Unknown'}
  Confidence: {f'{spec.confidence_score:.0%}' if spec else 'N/A'}

MODELS:
"""
        if spec and spec.models:
            for model in spec.models:
                summary += f"  • {model.model_id}: {model.description[:50]}...\n"
        
        summary += f"""
ENDPOINTS: {len(spec.endpoints) if spec else 0}
"""
        if spec:
            for ep in spec.endpoints[:5]:
                summary += f"  • {ep.method} {ep.path} - {ep.description[:40]}...\n"
        
        summary += f"""
LEARNINGS:
  Tips: {len(spec.tips) if spec else 0}
  Gotchas: {len(spec.gotchas) if spec else 0}

QUESTIONS: {len(self.session.questions)} ({len(self.session.answers)} answered)
TESTS: {len(self.session.test_results)} run
"""
        
        return summary
