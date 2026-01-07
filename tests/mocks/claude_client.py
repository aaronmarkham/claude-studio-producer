"""Mock Claude client for testing"""

import json
import random
from typing import Optional, List, Dict


class MockClaudeClient:
    """
    Mock ClaudeClient that returns realistic responses without hitting API
    This replaces the _generate_mock_response logic in production code
    """

    def __init__(self, debug: bool = False):
        self.debug = debug
        self.calls: List[Dict] = []  # Track calls for test assertions
        self.responses: List[str] = []  # Queue of responses to return
        self.response_index: int = 0  # Current response index

    def add_response(self, response: str):
        """Add a response to the queue"""
        self.responses.append(response)

    async def query(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """Generate mock response based on prompt patterns"""

        self.calls.append({"prompt": prompt, "system_prompt": system_prompt})

        if self.debug:
            print(f"[MockClaudeClient] Received prompt ({len(prompt)} chars)")

        # If responses queued, return next one
        if self.responses and self.response_index < len(self.responses):
            response = self.responses[self.response_index]
            self.response_index += 1
            return response

        # Producer: planning pilots
        if "pilot strategies" in prompt.lower() and "total_scenes_estimated" in prompt:
            return json.dumps({
                "total_scenes_estimated": 10,
                "pilots": [
                    {
                        "pilot_id": "pilot_budget",
                        "tier": "motion_graphics",
                        "allocated_budget": 60.0,
                        "test_scene_count": 2,
                        "rationale": "Cost-effective approach"
                    },
                    {
                        "pilot_id": "pilot_quality",
                        "tier": "animated",
                        "allocated_budget": 90.0,
                        "test_scene_count": 2,
                        "rationale": "Higher quality approach"
                    }
                ]
            })

        # ScriptWriter: creating scenes
        elif "ESTIMATED SCENES" in prompt or "scene_id" in prompt:
            num_scenes = 2
            scenes = []
            for i in range(num_scenes):
                scenes.append({
                    "scene_id": f"scene_{i+1}",
                    "title": f"Scene {i+1}",
                    "description": "Compelling visual sequence",
                    "duration": 5.0,
                    "visual_elements": ["element1", "element2"],
                    "audio_notes": "Background music",
                    "transition_in": "fade_in" if i == 0 else "cut",
                    "transition_out": "cut" if i < num_scenes-1 else "fade_out",
                    "prompt_hints": ["professional", "engaging"]
                })
            return json.dumps({"scenes": scenes})

        # Critic: evaluating pilots
        elif "gap analysis" in prompt.lower():
            score = random.randint(75, 95)
            return json.dumps({
                "overall_score": score,
                "gap_analysis": {
                    "matched_elements": ["visual style", "pacing"],
                    "missing_elements": [],
                    "quality_issues": ["minor adjustments needed"]
                },
                "decision": "continue",
                "budget_multiplier": 0.75 if score < 85 else 1.0,
                "reasoning": f"Score: {score}/100. Proceeding.",
                "adjustments_needed": ["Fine-tune color grading"]
            })

        # Default
        return json.dumps({"status": "mock_response"})

    def reset(self):
        """Reset call tracking (for test cleanup)"""
        self.calls.clear()
        self.responses.clear()
        self.response_index = 0

    def assert_called_with_prompt_containing(self, substring: str):
        """Assert any call contained substring in prompt"""
        for call in self.calls:
            if substring.lower() in call["prompt"].lower():
                return True
        raise AssertionError(f"No call with prompt containing '{substring}'")

    def get_call_count(self) -> int:
        """Get number of calls made"""
        return len(self.calls)
