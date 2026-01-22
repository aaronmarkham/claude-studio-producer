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
    
    # Discovery
    docs_analyzed: List[str] = field(default_factory=list)
    spec: Optional[ProviderSpec] = None
    
    # Questions and clarifications
    questions: List[Dict[str, str]] = field(default_factory=list)
    answers: List[Dict[str, str]] = field(default_factory=list)
    
    # Implementation
    stub_path: Optional[str] = None
    implementation_path: Optional[str] = None
    
    # Testing
    test_results: List[Dict[str, Any]] = field(default_factory=list)
    
    # Learnings
    learnings: List[str] = field(default_factory=list)


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
            json_match = re.search(r'\{[\s\S]*\}', response)
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
            context_parts.append(f"BASE CLASS:\n```python\n{base_class_code}\n```")
        
        context = "\n\n".join(context_parts)
        
        prompt = f"""Generate a complete Python provider implementation based on this specification.

PROVIDER SPECIFICATION:
{json.dumps(self._spec_to_dict(spec), indent=2)}

{context}

REQUIREMENTS:
1. Inherit from the appropriate base class (VideoProvider, AudioProvider, etc.)
2. Implement all required abstract methods
3. Handle authentication using environment variables
4. Implement proper error handling and retries
5. Support async/await patterns
6. Include comprehensive docstrings
7. Follow the existing codebase patterns

For async providers (async_poll), implement:
- Job submission
- Polling with exponential backoff
- Timeout handling
- Progress callbacks if possible

Generate the complete implementation file with all imports."""

        response = await self.claude.query(prompt)
        
        # Extract code block
        code_match = re.search(r'```python\n([\s\S]*?)\n```', response)
        if code_match:
            return code_match.group(1)
        
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

Return JSON array of test cases:
[
    {{
        "name": "test_basic_generation",
        "description": "Test basic text-to-video generation",
        "test_type": "unit|integration|e2e",
        "inputs": {{"prompt": "A sunset over mountains", "duration": 5}},
        "expected_behavior": "Should return a video URL",
        "assertions": ["result.video_url is not None", "result.duration >= 5"],
        "mock_response": {{...}}
    }}
]

Include:
1. Happy path tests
2. Error handling tests
3. Edge cases (empty input, max duration, etc.)
4. Authentication tests"""

        response = await self.claude.query(prompt)
        
        try:
            json_match = re.search(r'\[[\s\S]*\]', response)
            if json_match:
                return json.loads(json_match.group())
        except json.JSONDecodeError:
            pass
        
        return []
    
    async def run_test(
        self,
        test_case: Dict[str, Any],
        provider_instance: Any,
    ) -> Dict[str, Any]:
        """Run a single test case"""
        
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
            
            # Call the provider's generate method
            if hasattr(provider_instance, "generate"):
                output = await provider_instance.generate(**inputs)
                result["output"] = str(output)
                result["status"] = "passed"
            else:
                result["status"] = "skipped"
                result["error"] = "Provider has no generate method"
                
        except Exception as e:
            result["status"] = "failed"
            result["error"] = str(e)
        
        result["duration_ms"] = int((time.time() - start) * 1000)
        return result


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
    """
    
    def __init__(self, claude_client, memory_manager=None):
        self.claude = claude_client
        self.memory = memory_manager
        
        self.doc_analyzer = DocAnalyzer(claude_client)
        self.stub_analyzer = StubAnalyzer(claude_client)
        self.code_generator = ProviderCodeGenerator(claude_client)
        self.tester = ProviderTester(claude_client)
        
        self.session: Optional[OnboardingSession] = None
    
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
        
        # Step 3: Generate questions if confidence is low
        if self.session.spec and self.session.spec.confidence_score < 0.7:
            questions = await self._generate_questions()
            self.session.questions = questions
            print(f"❓ {len(questions)} questions need clarification")
        
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
            json_match = re.search(r'\[[\s\S]*\]', response)
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
        
        # Load base class if we have a stub
        base_class_code = None
        stub_analysis = None
        
        if self.session.stub_path:
            stub_analysis = await self.stub_analyzer.analyze_stub(self.session.stub_path)
            
            # Try to load base class
            base_class = stub_analysis.get("base_class", "")
            if base_class:
                base_class_code = await self._load_base_class(base_class)
        
        # Generate code
        implementation = await self.code_generator.generate_implementation(
            self.session.spec,
            stub_analysis=stub_analysis,
            base_class_code=base_class_code,
        )
        
        # Save if output path provided
        if output_path:
            Path(output_path).write_text(implementation)
            self.session.implementation_path = output_path
            print(f"💾 Saved implementation to {output_path}")
        
        return implementation
    
    async def _load_base_class(self, class_name: str) -> Optional[str]:
        """Load base class source code"""
        
        # Map common base classes to their files
        base_class_map = {
            "VideoProvider": "core/providers/video/base.py",
            "AudioProvider": "core/providers/audio/base.py",
            "TTSProvider": "core/providers/tts/base.py",
        }
        
        file_path = base_class_map.get(class_name)
        if file_path and Path(file_path).exists():
            return Path(file_path).read_text()
        
        return None
    
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
        
        results = []
        for test in test_cases:
            print(f"\n  Running: {test['name']}")
            print(f"  Description: {test['description']}")
            
            if interactive:
                user_input = input("  Run this test? [y/n/s(kip all)]: ").lower()
                if user_input == 's':
                    break
                if user_input != 'y':
                    continue
            
            # For now, just record the test case (actual execution requires imports)
            result = {
                "name": test["name"],
                "status": "recorded",
                "test_case": test,
            }
            results.append(result)
            self.session.test_results.append(result)
        
        return results
    
    async def record_learnings(self):
        """Record learnings from the onboarding session to memory"""
        
        if not self.memory or not self.session:
            return
        
        spec = self.session.spec
        
        # Record provider tips
        for tip in spec.tips:
            await self.memory.record_provider_learning(
                provider=spec.name,
                learning_type="tip",
                content=tip,
                promote_to_level="org",  # Provider knowledge is org-level
            )
        
        # Record gotchas as "avoid"
        for gotcha in spec.gotchas:
            await self.memory.record_provider_learning(
                provider=spec.name,
                learning_type="avoid",
                content=gotcha,
                severity="medium",
                promote_to_level="org",
            )
        
        # Record model limitations
        for model in spec.models:
            for limitation in model.limitations:
                await self.memory.record_provider_learning(
                    provider=spec.name,
                    learning_type="avoid",
                    content=f"[{model.model_id}] {limitation}",
                    promote_to_level="org",
                )
        
        self.session.status = "completed"
        print(f"📝 Recorded {len(spec.tips) + len(spec.gotchas)} learnings to memory")
    
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
