"""Bootstrap initial provider knowledge from known best practices"""

from core.models.memory import ProviderKnowledge


# Initial Luma knowledge based on known behaviors and learnings
INITIAL_LUMA_KNOWLEDGE = ProviderKnowledge(
    provider="luma",
    total_runs=0,  # Set to 0 so it doesn't affect averages
    avg_adherence=70,
    avg_quality=75,
    known_strengths=[
        "Realistic scenes and natural movements",
        "Slow camera movements (zoom, pan, orbit)",
        "Single subject focus with clear composition",
        "Atmospheric lighting and mood",
        "Image-to-video animation from seed frames",
        "Cinematic film-style shots",
        "Natural environments and landscapes",
    ],
    known_weaknesses=[
        "Text and readable writing - always appears garbled",
        "Abstract conceptual descriptions",
        "Multiple characters with choreography",
        "Complex multi-step actions in one shot",
        "Specific logos or brand elements",
        "Technical diagrams or UI elements",
        "Fast-paced action sequences",
    ],
    prompt_guidelines=[
        "Keep prompts to 3-4 sentences maximum",
        "Use concrete visual descriptions, not abstract concepts",
        "Specify camera motion explicitly (slow zoom in, tracking shot, orbit)",
        "Describe lighting and mood (soft morning light, neon glow, golden hour)",
        "Use film keywords: cinematic, film still, captured by ARRI Alexa",
        "Focus on real-world scenarios and natural movements",
        "Describe one clear subject or action per scene",
        "Include atmospheric details: fog, particles, lens flare",
    ],
    avoid_list=[
        "Abstract visualizations or conceptual descriptions",
        "Specific text, words, or readable writing in visuals",
        "Complex choreography with multiple characters",
        "Technical diagrams, flowcharts, or UI elements",
        "Long complex prompts - keep it simple and visual",
        "Asking for specific emotions or expressions",
        "Rapid scene changes or transitions within one generation",
    ],
    best_prompt_patterns=[
        "Cinematic shot of [subject] with [camera motion], [lighting]",
        "Slow zoom into [subject] with soft [lighting] and gentle [atmosphere]",
        "Tracking shot following [subject] through [environment]",
        "Close-up of [subject] with shallow depth of field",
        "Wide establishing shot of [environment] at [time of day]",
    ],
    optimal_settings={
        "duration": 5,  # 5 seconds is optimal
        "resolution": "720p",
        "aspect_ratio": "16:9",
    },
    recent_learnings=[],
)


# Initial Runway knowledge
INITIAL_RUNWAY_KNOWLEDGE = ProviderKnowledge(
    provider="runway",
    total_runs=0,
    avg_adherence=72,
    avg_quality=78,
    known_strengths=[
        "Smooth motion and transitions",
        "Good at stylized/artistic content",
        "Handles creative visual effects well",
        "Consistent quality across generations",
    ],
    known_weaknesses=[
        "Text rendering is unreliable",
        "Complex scenes with many elements",
        "Precise timing requirements",
    ],
    prompt_guidelines=[
        "Be specific about visual style",
        "Describe motion direction and speed",
        "Keep scenes simple and focused",
    ],
    avoid_list=[
        "Readable text in visuals",
        "Overly complex multi-element scenes",
    ],
    best_prompt_patterns=[
        "[Subject] moving [direction] with [visual style]",
        "Stylized [scene] with [effect] and [atmosphere]",
    ],
    optimal_settings={
        "duration": 4,
        "resolution": "720p",
    },
    recent_learnings=[],
)


# All initial knowledge
INITIAL_PROVIDER_KNOWLEDGE = {
    "luma": INITIAL_LUMA_KNOWLEDGE,
    "runway": INITIAL_RUNWAY_KNOWLEDGE,
}


async def bootstrap_all_providers(memory_manager):
    """Bootstrap initial knowledge for all known providers"""
    for provider, knowledge in INITIAL_PROVIDER_KNOWLEDGE.items():
        await memory_manager.bootstrap_provider_knowledge(provider, knowledge)
