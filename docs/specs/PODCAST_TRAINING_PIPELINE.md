# Podcast Training Pipeline Specification

## Overview

A training pipeline that learns the "shape" of good technical podcast explainers from human-created examples. Uses paired (PDF, MP3) training data to extract patterns, calibrate prompts, and iteratively improve generation quality through measurable loss metrics.

```
TRAINING PHILOSOPHY: "Learn from the Masters"

Training Data:
├── optimal-adversarial-texts-full.pdf + .mp3
├── agentic-information-retrieval.pdf + .mp3  
├── [female voice pair 1]
└── [female voice pair 2]

Output:
├── Calibrated prompt templates
├── Style profiles in memory
├── Segment structure templates
├── Loss convergence metrics
```

---

# Part 1: Training Data Ingestion

## 1.1 PDF Ingestion (Existing Pipeline)

Use existing KB ingestion to extract DocumentGraph:

```bash
claude-studio kb create "podcast-training"
claude-studio kb add podcast-training --paper artifacts/training_data/optimal-adversarial-texts-full.pdf
claude-studio kb add podcast-training --paper artifacts/training_data/agentic-information-retrieval.pdf
# ... add other pairs
```

This gives us:
- DocumentAtoms (text, figures, tables, equations)
- Extracted figures as image files
- Key claims and entities
- Document structure

## 1.2 Audio Transcription (New)

```python
@dataclass
class TranscriptionResult:
    """Result of transcribing a podcast MP3"""
    source_path: str
    transcript_text: str
    
    # Word-level timing (for alignment)
    word_timestamps: List[WordTimestamp]
    
    # Detected segments with timing
    segments: List[TranscriptSegment]
    
    # Audio metadata
    total_duration: float
    speaker_id: Optional[str]  # For multi-speaker detection
    
    # Quality metrics
    confidence: float
    language: str


@dataclass
class WordTimestamp:
    """Individual word with timing"""
    word: str
    start_time: float
    end_time: float
    confidence: float


@dataclass  
class TranscriptSegment:
    """A segment of the transcript (sentence or paragraph level)"""
    segment_id: str
    text: str
    start_time: float
    end_time: float
    duration: float
    
    # Detected type (filled in by analysis phase)
    segment_type: Optional[str] = None  # "intro", "background", "explanation", etc.
    
    # Linked to PDF atoms (filled in by alignment phase)
    linked_atoms: List[str] = field(default_factory=list)
```

### Transcription Implementation

```python
async def transcribe_podcast(
    audio_path: str,
    model: str = "whisper-large-v3",
) -> TranscriptionResult:
    """
    Transcribe podcast audio with word-level timestamps.
    
    Options:
    - OpenAI Whisper API (cloud, fast)
    - whisper.cpp (local, free)
    - AssemblyAI (cloud, good timestamps)
    """
    
    # Using OpenAI Whisper API with timestamps
    from openai import OpenAI
    client = OpenAI()
    
    with open(audio_path, "rb") as f:
        response = client.audio.transcriptions.create(
            model="whisper-1",
            file=f,
            response_format="verbose_json",
            timestamp_granularities=["word", "segment"]
        )
    
    # Parse into our structure
    word_timestamps = [
        WordTimestamp(
            word=w["word"],
            start_time=w["start"],
            end_time=w["end"],
            confidence=w.get("confidence", 1.0)
        )
        for w in response.words
    ]
    
    segments = [
        TranscriptSegment(
            segment_id=f"seg_{i}",
            text=s["text"],
            start_time=s["start"],
            end_time=s["end"],
            duration=s["end"] - s["start"],
        )
        for i, s in enumerate(response.segments)
    ]
    
    return TranscriptionResult(
        source_path=audio_path,
        transcript_text=response.text,
        word_timestamps=word_timestamps,
        segments=segments,
        total_duration=segments[-1].end_time if segments else 0,
        confidence=sum(w.confidence for w in word_timestamps) / len(word_timestamps),
        language=response.language,
    )
```

## 1.3 Training Pair Model

```python
@dataclass
class TrainingPair:
    """A paired PDF + podcast for training"""
    pair_id: str
    
    # Source files
    pdf_path: str
    audio_path: str
    
    # Extracted content
    document_graph: DocumentGraph
    transcription: TranscriptionResult
    
    # Analysis results (filled in Phase 2)
    aligned_segments: List[AlignedSegment] = None
    structure_profile: StructureProfile = None
    style_profile: StyleProfile = None
    
    # Metadata
    speaker_gender: str  # "male", "female"
    source: str  # "journalclub"
    duration_minutes: float


@dataclass
class AlignedSegment:
    """A transcript segment aligned to PDF content"""
    segment_id: str
    transcript_segment: TranscriptSegment
    
    # What PDF content this segment discusses
    primary_atoms: List[str]      # Main atoms being discussed
    referenced_figures: List[str]  # Figures mentioned or relevant
    
    # Segment classification
    segment_type: SegmentType
    
    # Content analysis
    key_concepts: List[str]
    technical_terms: List[str]
    analogies_used: List[str]
    questions_asked: List[str]
    
    # Timing
    words_per_minute: float
    density_score: float  # How much content per second
```

---

# Part 2: Analysis Phase

## 2.1 Segment Type Detection

```python
class SegmentType(Enum):
    """Types of podcast segments"""
    INTRO = "intro"                    # Welcome, paper intro
    BACKGROUND = "background"          # Context, prior work
    PROBLEM_STATEMENT = "problem"      # What problem paper addresses
    METHODOLOGY = "methodology"        # How they did it
    KEY_FINDING = "key_finding"        # Main results
    FIGURE_DISCUSSION = "figure"       # Discussing a specific figure
    IMPLICATION = "implication"        # Why it matters
    LIMITATION = "limitation"          # Caveats, future work
    CONCLUSION = "conclusion"          # Wrap up
    TANGENT = "tangent"               # Interesting aside
    TRANSITION = "transition"          # Moving between topics


async def classify_segments(
    transcription: TranscriptionResult,
    document_graph: DocumentGraph,
) -> List[AlignedSegment]:
    """
    Use LLM to classify each transcript segment and align to PDF atoms.
    """
    
    prompt = f"""Analyze this podcast transcript segment by segment.
    
TRANSCRIPT:
{transcription.transcript_text}

PAPER STRUCTURE:
Title: {document_graph.title}
Abstract: {document_graph.abstract}
Sections: {[s.title for s in document_graph.sections]}
Figures: {[f.caption for f in document_graph.get_figures()]}

For each segment, identify:
1. segment_type: One of {[t.value for t in SegmentType]}
2. primary_atoms: Which parts of the paper this discusses
3. referenced_figures: Any figures mentioned or relevant
4. key_concepts: Main ideas in this segment
5. technical_terms: Jargon/technical vocabulary used
6. analogies_used: Any analogies or metaphors
7. questions_asked: Rhetorical or actual questions

Return as JSON array of segment analyses.
"""
    
    response = await llm.query(prompt, response_format="json")
    # Parse and return AlignedSegment list
```

## 2.2 Structure Profile Extraction

```python
@dataclass
class StructureProfile:
    """Extracted structure patterns from a podcast"""
    
    # Segment sequence
    segment_sequence: List[SegmentType]  # Actual sequence
    segment_counts: Dict[SegmentType, int]
    
    # Timing patterns
    total_duration: float
    segment_durations: Dict[SegmentType, List[float]]  # Duration per type
    avg_segment_duration: float
    
    # Content density
    words_per_minute: float
    concepts_per_minute: float
    figures_discussed: int
    figure_discussion_duration: float  # Total time on figures
    
    # Structure patterns
    intro_percentage: float      # % of time on intro
    methodology_percentage: float
    findings_percentage: float
    conclusion_percentage: float
    
    # Transition patterns
    transition_phrases: List[str]  # "Now let's look at...", "Moving on..."


async def extract_structure_profile(
    aligned_segments: List[AlignedSegment],
    transcription: TranscriptionResult,
) -> StructureProfile:
    """Extract structural patterns from analyzed podcast."""
    
    segment_sequence = [s.segment_type for s in aligned_segments]
    
    # Calculate timing distributions
    segment_durations = defaultdict(list)
    for seg in aligned_segments:
        segment_durations[seg.segment_type].append(seg.transcript_segment.duration)
    
    total_duration = transcription.total_duration
    word_count = len(transcription.transcript_text.split())
    
    return StructureProfile(
        segment_sequence=segment_sequence,
        segment_counts={t: segment_sequence.count(t) for t in SegmentType},
        total_duration=total_duration,
        segment_durations=dict(segment_durations),
        avg_segment_duration=total_duration / len(aligned_segments),
        words_per_minute=word_count / (total_duration / 60),
        concepts_per_minute=sum(len(s.key_concepts) for s in aligned_segments) / (total_duration / 60),
        figures_discussed=len([s for s in aligned_segments if s.segment_type == SegmentType.FIGURE_DISCUSSION]),
        # ... calculate percentages
    )
```

## 2.3 Style Profile Extraction

```python
@dataclass
class StyleProfile:
    """Extracted style patterns from a podcast"""
    
    # Voice characteristics
    speaker_id: str
    speaker_gender: str
    
    # Language patterns
    avg_sentence_length: float
    vocabulary_complexity: float  # 0-1, based on word rarity
    jargon_density: float        # % technical terms
    
    # Engagement markers
    questions_per_minute: float
    analogies_per_segment: float
    enthusiasm_markers: List[str]  # "fascinating", "remarkable", "this is key"
    
    # Explanation patterns
    definition_style: str         # "inline", "parenthetical", "before_use"
    example_frequency: float      # Examples per concept
    
    # Phrasing templates
    intro_phrases: List[str]      # "Today we're looking at..."
    transition_phrases: List[str]  # "Now, turning to..."
    emphasis_phrases: List[str]   # "This is crucial because..."
    conclusion_phrases: List[str]  # "So what does this mean?"
    
    # Figure discussion style
    figure_intro_pattern: str     # How they introduce figures
    figure_explanation_depth: str  # "brief", "moderate", "detailed"


async def extract_style_profile(
    aligned_segments: List[AlignedSegment],
    transcription: TranscriptionResult,
    speaker_gender: str,
) -> StyleProfile:
    """Extract style patterns using LLM analysis."""
    
    prompt = f"""Analyze the speaking style of this podcast transcript.

TRANSCRIPT:
{transcription.transcript_text}

Extract:
1. Common phrases used to:
   - Introduce the paper
   - Transition between topics
   - Emphasize important points
   - Discuss figures
   - Conclude sections
   
2. Explanation style:
   - How are technical terms defined?
   - How many examples per concept?
   - Analogy usage patterns
   
3. Engagement techniques:
   - Question frequency and types
   - Enthusiasm markers
   - Listener engagement phrases

4. Language complexity:
   - Average sentence length
   - Technical term density
   - Vocabulary level

Return as structured JSON.
"""
    
    response = await llm.query(prompt, response_format="json")
    # Parse into StyleProfile
```

---

# Part 3: Profile Synthesis

## 3.1 Aggregate Profiles

```python
@dataclass
class AggregatedProfile:
    """Combined profile from all training pairs"""
    
    # Structure template
    canonical_segment_sequence: List[SegmentType]
    segment_duration_targets: Dict[SegmentType, Tuple[float, float]]  # (min, max)
    
    # Timing targets by depth level
    depth_targets: Dict[PodcastDepth, DepthTarget]
    
    # Style variations (by speaker/gender)
    style_variants: Dict[str, StyleProfile]
    
    # Common patterns
    universal_intro_patterns: List[str]
    universal_transition_patterns: List[str]
    universal_figure_patterns: List[str]
    
    # Quality thresholds learned from data
    min_coverage: float          # Minimum concept coverage
    target_words_per_minute: Tuple[float, float]  # (min, max) WPM range
    target_concepts_per_minute: Tuple[float, float]
    
    # Version tracking
    version: str
    training_pairs_used: List[str]
    created_at: datetime


@dataclass
class DepthTarget:
    """Targets for a specific depth level"""
    depth: PodcastDepth
    
    duration_range: Tuple[float, float]  # seconds
    segment_count_range: Tuple[int, int]
    concepts_per_segment: Tuple[int, int]
    figure_coverage: float  # % of figures to discuss
    
    # Derived from training data analysis
    example_pair_ids: List[str]  # Which training pairs match this depth


class PodcastDepth(Enum):
    OVERVIEW = "overview"           # 3-5 min
    STANDARD = "standard"           # 10-15 min (target)
    DEEP_DIVE = "deep_dive"         # 20-30 min
    COMPREHENSIVE = "comprehensive" # 45+ min


async def synthesize_profiles(
    training_pairs: List[TrainingPair],
) -> AggregatedProfile:
    """
    Combine individual profiles into unified template.
    """
    
    # Collect all structure profiles
    structures = [p.structure_profile for p in training_pairs]
    styles = [p.style_profile for p in training_pairs]
    
    # Find common segment sequence pattern
    # (Use sequence alignment or LLM to find canonical order)
    canonical_sequence = find_canonical_sequence(
        [s.segment_sequence for s in structures]
    )
    
    # Calculate duration targets from data
    segment_durations = defaultdict(list)
    for struct in structures:
        for seg_type, durations in struct.segment_durations.items():
            segment_durations[seg_type].extend(durations)
    
    duration_targets = {
        seg_type: (min(durs), max(durs))
        for seg_type, durs in segment_durations.items()
    }
    
    # Group styles by speaker
    style_variants = {}
    for pair in training_pairs:
        key = f"{pair.speaker_gender}_{pair.pair_id}"
        style_variants[key] = pair.style_profile
    
    # Extract common patterns
    universal_intro = find_common_phrases([s.intro_phrases for s in styles])
    universal_transition = find_common_phrases([s.transition_phrases for s in styles])
    
    return AggregatedProfile(
        canonical_segment_sequence=canonical_sequence,
        segment_duration_targets=duration_targets,
        depth_targets=calculate_depth_targets(structures),
        style_variants=style_variants,
        universal_intro_patterns=universal_intro,
        universal_transition_patterns=universal_transition,
        # ...
    )
```

## 3.2 Store in Memory

```python
async def store_profile_in_memory(
    profile: AggregatedProfile,
    memory_manager: MemoryManager,
):
    """Store aggregated profile in memory for agent use."""
    
    namespace = "/org/default/learnings/podcast_profiles"
    
    await memory_manager.store(
        namespace=namespace,
        key=f"profile_v{profile.version}",
        data=profile.to_dict(),
        metadata={
            "type": "podcast_profile",
            "training_pairs": profile.training_pairs_used,
            "created_at": profile.created_at.isoformat(),
        }
    )
    
    # Also store individual components for easy retrieval
    await memory_manager.store(
        namespace=f"{namespace}/structure",
        key="canonical_sequence",
        data={"sequence": [s.value for s in profile.canonical_segment_sequence]}
    )
    
    await memory_manager.store(
        namespace=f"{namespace}/style",
        key="patterns",
        data={
            "intro": profile.universal_intro_patterns,
            "transition": profile.universal_transition_patterns,
            "figure": profile.universal_figure_patterns,
        }
    )
```

---

# Part 4: Training Loop

## 4.1 Loss Metrics

```python
@dataclass
class LossMetrics:
    """Metrics for evaluating generated podcast quality"""
    
    # Duration loss (lower is better)
    duration_loss: float          # |generated - reference| / reference
    duration_generated: float
    duration_reference: float
    
    # Coverage loss (lower is better)
    coverage_loss: float          # 1 - (concepts_mentioned / total_concepts)
    concepts_mentioned: int
    concepts_total: int
    concepts_missed: List[str]
    
    # Structure loss (lower is better)
    structure_loss: float         # 1 - alignment_score
    segment_type_accuracy: float  # % segments matching expected type
    sequence_similarity: float    # Edit distance normalized
    
    # Quality scores (higher is better, inverted for loss)
    engagement_score: float       # 0-100 from LLM judge
    clarity_score: float          # 0-100 from LLM judge
    accuracy_score: float         # 0-100 from LLM judge
    quality_loss: float           # (300 - sum(scores)) / 300
    
    # ROUGE scores (higher is better)
    rouge_1: float               # Unigram overlap
    rouge_2: float               # Bigram overlap
    rouge_l: float               # Longest common subsequence
    rouge_loss: float            # 1 - avg(rouge scores)
    
    # Combined loss
    total_loss: float            # Weighted combination
    
    # Metadata
    trial_id: str
    pair_id: str
    generated_at: datetime


def calculate_total_loss(metrics: LossMetrics, weights: Dict[str, float] = None) -> float:
    """
    Calculate weighted total loss.
    
    Default weights emphasize duration and coverage (what user asked for).
    """
    weights = weights or {
        "duration": 0.25,
        "coverage": 0.25,
        "structure": 0.20,
        "quality": 0.20,
        "rouge": 0.10,
    }
    
    return (
        weights["duration"] * metrics.duration_loss +
        weights["coverage"] * metrics.coverage_loss +
        weights["structure"] * metrics.structure_loss +
        weights["quality"] * metrics.quality_loss +
        weights["rouge"] * metrics.rouge_loss
    )
```

## 4.2 Individual Loss Calculations

### Duration Loss

```python
def calculate_duration_loss(
    generated_duration: float,
    reference_duration: float,
) -> Tuple[float, Dict]:
    """
    Calculate how close generated duration is to reference.
    
    Returns:
        loss: Normalized difference (0 = perfect match)
        details: Breakdown of calculation
    """
    diff = abs(generated_duration - reference_duration)
    loss = diff / reference_duration
    
    return loss, {
        "generated_seconds": generated_duration,
        "reference_seconds": reference_duration,
        "diff_seconds": diff,
        "diff_percentage": loss * 100,
    }
```

### Coverage Loss

```python
async def calculate_coverage_loss(
    generated_transcript: str,
    document_graph: DocumentGraph,
) -> Tuple[float, Dict]:
    """
    Calculate what percentage of key concepts were covered.
    
    Uses LLM to check if each key concept from the paper
    is mentioned/explained in the generated transcript.
    """
    
    # Extract key concepts from paper
    key_concepts = extract_key_concepts(document_graph)
    
    prompt = f"""Check which concepts from this paper are covered in the podcast transcript.

PAPER KEY CONCEPTS:
{json.dumps(key_concepts, indent=2)}

PODCAST TRANSCRIPT:
{generated_transcript}

For each concept, determine:
- covered: true/false (is it mentioned or explained?)
- depth: "not_mentioned" | "briefly_mentioned" | "explained" | "deeply_explained"

Return JSON: {{"concepts": [{{"concept": "...", "covered": true, "depth": "explained"}}]}}
"""
    
    response = await llm.query(prompt, response_format="json")
    results = response["concepts"]
    
    covered = [c for c in results if c["covered"]]
    coverage_ratio = len(covered) / len(key_concepts)
    
    return 1 - coverage_ratio, {
        "concepts_total": len(key_concepts),
        "concepts_covered": len(covered),
        "concepts_missed": [c["concept"] for c in results if not c["covered"]],
        "coverage_by_depth": {
            "deeply_explained": len([c for c in covered if c["depth"] == "deeply_explained"]),
            "explained": len([c for c in covered if c["depth"] == "explained"]),
            "briefly_mentioned": len([c for c in covered if c["depth"] == "briefly_mentioned"]),
        }
    }
```

### Structure Loss

```python
async def calculate_structure_loss(
    generated_segments: List[ScriptSegment],
    reference_aligned: List[AlignedSegment],
) -> Tuple[float, Dict]:
    """
    Calculate structural similarity to reference.
    """
    
    gen_sequence = [s.segment_type for s in generated_segments]
    ref_sequence = [s.segment_type for s in reference_aligned]
    
    # Sequence similarity using edit distance
    edit_distance = levenshtein_distance(gen_sequence, ref_sequence)
    max_len = max(len(gen_sequence), len(ref_sequence))
    sequence_similarity = 1 - (edit_distance / max_len)
    
    # Segment type distribution similarity
    gen_dist = Counter(gen_sequence)
    ref_dist = Counter(ref_sequence)
    
    all_types = set(gen_dist.keys()) | set(ref_dist.keys())
    dist_similarity = 1 - sum(
        abs(gen_dist.get(t, 0) - ref_dist.get(t, 0)) 
        for t in all_types
    ) / (len(gen_sequence) + len(ref_sequence))
    
    # Combined structure loss
    structure_loss = 1 - (0.6 * sequence_similarity + 0.4 * dist_similarity)
    
    return structure_loss, {
        "sequence_similarity": sequence_similarity,
        "distribution_similarity": dist_similarity,
        "edit_distance": edit_distance,
        "generated_segment_count": len(gen_sequence),
        "reference_segment_count": len(ref_sequence),
    }
```

### Quality Loss (LLM as Judge)

```python
async def calculate_quality_loss(
    generated_transcript: str,
    reference_transcript: str,
    document_graph: DocumentGraph,
) -> Tuple[float, Dict]:
    """
    Use LLM to judge quality on engagement, clarity, accuracy.
    """
    
    prompt = f"""You are evaluating a generated podcast transcript against a human-created reference.

PAPER BEING DISCUSSED:
Title: {document_graph.title}
Abstract: {document_graph.abstract}

REFERENCE TRANSCRIPT (human-created, gold standard):
{reference_transcript[:3000]}...

GENERATED TRANSCRIPT (to evaluate):
{generated_transcript[:3000]}...

Score the GENERATED transcript on these criteria (0-100 each):

1. ENGAGEMENT: How engaging and interesting is it?
   - Does it use questions, analogies, enthusiasm markers?
   - Would a listener stay interested?
   
2. CLARITY: How clear are the explanations?
   - Are technical terms defined?
   - Is the structure logical?
   - Are examples used effectively?
   
3. ACCURACY: How faithful is it to the paper?
   - Are claims accurate?
   - Are nuances preserved?
   - Any misrepresentations?

Also note:
- What does the reference do better?
- What does the generated version do well?
- Specific suggestions for improvement

Return JSON:
{{
    "engagement_score": 75,
    "clarity_score": 80,
    "accuracy_score": 85,
    "reference_strengths": ["...", "..."],
    "generated_strengths": ["...", "..."],
    "improvement_suggestions": ["...", "..."]
}}
"""
    
    response = await llm.query(prompt, response_format="json")
    
    scores = [
        response["engagement_score"],
        response["clarity_score"],
        response["accuracy_score"],
    ]
    quality_loss = (300 - sum(scores)) / 300
    
    return quality_loss, {
        "engagement_score": response["engagement_score"],
        "clarity_score": response["clarity_score"],
        "accuracy_score": response["accuracy_score"],
        "reference_strengths": response["reference_strengths"],
        "generated_strengths": response["generated_strengths"],
        "improvement_suggestions": response["improvement_suggestions"],
    }
```

### ROUGE Scores

```python
def calculate_rouge_loss(
    generated_transcript: str,
    reference_transcript: str,
) -> Tuple[float, Dict]:
    """
    Calculate ROUGE scores for text similarity.
    
    ROUGE (Recall-Oriented Understudy for Gisting Evaluation):
    - ROUGE-1: Unigram (single word) overlap
    - ROUGE-2: Bigram (two word) overlap  
    - ROUGE-L: Longest common subsequence
    
    Higher ROUGE = more similar to reference.
    For loss, we use 1 - ROUGE.
    
    INTERPRETATION:
    - ROUGE-1 > 0.4: Good word-level similarity
    - ROUGE-2 > 0.2: Good phrase-level similarity
    - ROUGE-L > 0.3: Good structural similarity
    """
    from rouge_score import rouge_scorer
    
    scorer = rouge_scorer.RougeScorer(['rouge1', 'rouge2', 'rougeL'], use_stemmer=True)
    scores = scorer.score(reference_transcript, generated_transcript)
    
    rouge_1 = scores['rouge1'].fmeasure
    rouge_2 = scores['rouge2'].fmeasure
    rouge_l = scores['rougeL'].fmeasure
    
    avg_rouge = (rouge_1 + rouge_2 + rouge_l) / 3
    rouge_loss = 1 - avg_rouge
    
    return rouge_loss, {
        "rouge_1": rouge_1,
        "rouge_2": rouge_2,
        "rouge_l": rouge_l,
        "interpretation": {
            "rouge_1": "Good" if rouge_1 > 0.4 else "Needs improvement",
            "rouge_2": "Good" if rouge_2 > 0.2 else "Needs improvement",
            "rouge_l": "Good" if rouge_l > 0.3 else "Needs improvement",
        },
        "note": "ROUGE measures n-gram overlap with reference. Higher is more similar."
    }
```

## 4.3 Training Loop

```python
@dataclass
class TrainingConfig:
    """Configuration for training run"""
    max_trials: int = 10
    convergence_threshold: float = 0.05  # Stop if loss improves < 5%
    convergence_window: int = 3          # Check over last N trials
    
    # Loss weights
    loss_weights: Dict[str, float] = field(default_factory=lambda: {
        "duration": 0.25,
        "coverage": 0.25,
        "structure": 0.20,
        "quality": 0.20,
        "rouge": 0.10,
    })
    
    # Target depth for training
    target_depth: PodcastDepth = PodcastDepth.STANDARD


@dataclass
class TrialResult:
    """Result of a single training trial"""
    trial_id: str
    trial_number: int
    
    # Per-pair results
    pair_results: Dict[str, LossMetrics]
    
    # Aggregated metrics
    avg_total_loss: float
    avg_duration_loss: float
    avg_coverage_loss: float
    avg_structure_loss: float
    avg_quality_loss: float
    avg_rouge_loss: float
    
    # Generated artifacts (for review)
    generated_scripts: Dict[str, str]  # pair_id -> script path
    generated_audio: Dict[str, str]    # pair_id -> audio path
    
    # Prompt version used
    prompt_version: str
    profile_version: str
    
    timestamp: datetime


async def run_training_loop(
    training_pairs: List[TrainingPair],
    config: TrainingConfig,
    memory_manager: MemoryManager,
) -> List[TrialResult]:
    """
    Main training loop.
    
    1. For each trial:
       a. Generate podcast for each training pair
       b. Calculate loss metrics
       c. Store results
       d. Check convergence
       e. Refine prompts/profile if not converged
    
    2. Return all trial results for analysis
    """
    
    results: List[TrialResult] = []
    current_profile = await load_profile(memory_manager)
    current_prompts = await load_prompt_templates(memory_manager)
    
    for trial_num in range(config.max_trials):
        trial_id = f"trial_{trial_num:03d}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        console.print(f"\n{'='*60}")
        console.print(f"TRIAL {trial_num + 1}/{config.max_trials}")
        console.print(f"{'='*60}\n")
        
        pair_results = {}
        generated_scripts = {}
        generated_audio = {}
        
        for pair in training_pairs:
            console.print(f"\n--- Processing: {pair.pair_id} ---")
            
            # 1. Generate podcast script using current prompts/profile
            script = await generate_podcast_script(
                document_graph=pair.document_graph,
                profile=current_profile,
                prompts=current_prompts,
                target_depth=config.target_depth,
            )
            
            # 2. Generate TTS audio
            audio_path = await generate_audio(script, trial_id, pair.pair_id)
            generated_duration = await get_audio_duration(audio_path)
            
            # 3. Calculate all loss metrics
            metrics = await calculate_all_metrics(
                generated_script=script,
                generated_duration=generated_duration,
                reference_transcription=pair.transcription,
                reference_aligned=pair.aligned_segments,
                document_graph=pair.document_graph,
                trial_id=trial_id,
                pair_id=pair.pair_id,
                weights=config.loss_weights,
            )
            
            pair_results[pair.pair_id] = metrics
            generated_scripts[pair.pair_id] = script.script_path
            generated_audio[pair.pair_id] = audio_path
            
            # Log progress
            console.print(f"  Duration: {generated_duration:.1f}s (ref: {pair.transcription.total_duration:.1f}s)")
            console.print(f"  Coverage: {(1-metrics.coverage_loss)*100:.1f}%")
            console.print(f"  Quality: {100-metrics.quality_loss*100:.1f}/100")
            console.print(f"  Total Loss: {metrics.total_loss:.4f}")
        
        # 4. Aggregate trial results
        trial_result = TrialResult(
            trial_id=trial_id,
            trial_number=trial_num,
            pair_results=pair_results,
            avg_total_loss=np.mean([m.total_loss for m in pair_results.values()]),
            avg_duration_loss=np.mean([m.duration_loss for m in pair_results.values()]),
            avg_coverage_loss=np.mean([m.coverage_loss for m in pair_results.values()]),
            avg_structure_loss=np.mean([m.structure_loss for m in pair_results.values()]),
            avg_quality_loss=np.mean([m.quality_loss for m in pair_results.values()]),
            avg_rouge_loss=np.mean([m.rouge_loss for m in pair_results.values()]),
            generated_scripts=generated_scripts,
            generated_audio=generated_audio,
            prompt_version=current_prompts.version,
            profile_version=current_profile.version,
            timestamp=datetime.now(),
        )
        
        results.append(trial_result)
        
        # 5. Store trial results
        await store_trial_results(trial_result, memory_manager)
        
        # 6. Print trial summary
        print_trial_summary(trial_result)
        
        # 7. Check convergence
        if check_convergence(results, config):
            console.print(f"\n✓ Converged after {trial_num + 1} trials!")
            break
        
        # 8. Refine prompts/profile for next trial
        if trial_num < config.max_trials - 1:
            current_prompts, current_profile = await refine_for_next_trial(
                trial_result=trial_result,
                current_prompts=current_prompts,
                current_profile=current_profile,
                memory_manager=memory_manager,
            )
    
    # Final report
    await generate_training_report(results, config, memory_manager)
    
    return results


def check_convergence(
    results: List[TrialResult],
    config: TrainingConfig,
) -> bool:
    """Check if training has converged."""
    
    if len(results) < config.convergence_window + 1:
        return False
    
    recent = results[-config.convergence_window:]
    previous = results[-config.convergence_window - 1]
    
    # Check if improvement is below threshold
    avg_recent = np.mean([r.avg_total_loss for r in recent])
    improvement = (previous.avg_total_loss - avg_recent) / previous.avg_total_loss
    
    return improvement < config.convergence_threshold
```

## 4.4 Prompt Refinement

```python
async def refine_for_next_trial(
    trial_result: TrialResult,
    current_prompts: PromptTemplates,
    current_profile: AggregatedProfile,
    memory_manager: MemoryManager,
) -> Tuple[PromptTemplates, AggregatedProfile]:
    """
    Analyze trial results and refine prompts/profile.
    """
    
    # Collect improvement suggestions from all pairs
    all_suggestions = []
    for pair_id, metrics in trial_result.pair_results.items():
        if hasattr(metrics, 'improvement_suggestions'):
            all_suggestions.extend(metrics.improvement_suggestions)
    
    # Analyze patterns in failures
    prompt = f"""Analyze these training trial results and suggest prompt improvements.

CURRENT PROMPT TEMPLATE:
{current_prompts.script_writer_prompt}

TRIAL RESULTS:
{json.dumps({
    "avg_duration_loss": trial_result.avg_duration_loss,
    "avg_coverage_loss": trial_result.avg_coverage_loss,
    "avg_structure_loss": trial_result.avg_structure_loss,
    "avg_quality_loss": trial_result.avg_quality_loss,
}, indent=2)}

CONCEPTS FREQUENTLY MISSED:
{collect_missed_concepts(trial_result)}

LLM JUDGE SUGGESTIONS:
{all_suggestions}

Based on this analysis, provide:
1. Specific prompt modifications to improve weakest metrics
2. Any profile adjustments (duration targets, segment counts, etc.)
3. Reasoning for each change

Return JSON:
{{
    "prompt_modifications": [
        {{"section": "intro_instructions", "change": "...", "reason": "..."}},
    ],
    "profile_adjustments": [
        {{"parameter": "target_duration", "new_value": 720, "reason": "..."}},
    ],
    "priority_focus": "coverage" // which metric to prioritize
}}
"""
    
    response = await llm.query(prompt, response_format="json")
    
    # Apply modifications
    new_prompts = apply_prompt_modifications(
        current_prompts, 
        response["prompt_modifications"]
    )
    new_profile = apply_profile_adjustments(
        current_profile,
        response["profile_adjustments"]
    )
    
    # Increment versions
    new_prompts.version = f"v{int(current_prompts.version[1:]) + 1}"
    new_profile.version = f"v{int(current_profile.version[1:]) + 1}"
    
    # Store updated versions
    await memory_manager.store(
        namespace="/org/default/learnings/podcast_training/prompts",
        key=new_prompts.version,
        data=new_prompts.to_dict(),
    )
    
    return new_prompts, new_profile
```

---

# Part 5: Video Calibration

## 5.1 Asset Alignment

```python
@dataclass
class VisualAssetAlignment:
    """Alignment of visual assets to transcript timeline"""
    
    segment_id: str
    start_time: float
    end_time: float
    
    # Primary visual
    visual_type: str  # "figure", "quote_card", "title_card", "broll"
    
    # For figures
    figure_atom_id: Optional[str]
    figure_path: Optional[str]
    
    # For quote cards
    quote_text: Optional[str]
    quote_style: Optional[str]
    
    # Animation
    animation_type: str  # "ken_burns", "fade", "static"
    animation_params: Dict


async def align_visuals_to_transcript(
    aligned_segments: List[AlignedSegment],
    document_graph: DocumentGraph,
    transcription: TranscriptionResult,
) -> List[VisualAssetAlignment]:
    """
    Determine which visual to show at each point in the podcast.
    
    Rules:
    1. When discussing a figure → Show that figure (Ken Burns)
    2. When reading a quote → Show quote card with text
    3. When explaining concept → Show relevant figure or generated card
    4. Filler → Static title card or gentle animation
    """
    
    alignments = []
    figure_map = {f.atom_id: f for f in document_graph.get_figures()}
    
    for segment in aligned_segments:
        # Check if segment discusses a figure
        if segment.segment_type == SegmentType.FIGURE_DISCUSSION:
            figure_id = segment.referenced_figures[0] if segment.referenced_figures else None
            if figure_id and figure_id in figure_map:
                alignments.append(VisualAssetAlignment(
                    segment_id=segment.segment_id,
                    start_time=segment.transcript_segment.start_time,
                    end_time=segment.transcript_segment.end_time,
                    visual_type="figure",
                    figure_atom_id=figure_id,
                    figure_path=figure_map[figure_id].file_path,
                    animation_type="ken_burns",
                    animation_params={"zoom": 1.2, "pan": "center_to_detail"},
                ))
                continue
        
        # Check for quotable content
        if segment.segment_type == SegmentType.KEY_FINDING:
            # Extract key quote from segment
            key_quote = extract_key_quote(segment.transcript_segment.text)
            if key_quote:
                alignments.append(VisualAssetAlignment(
                    segment_id=segment.segment_id,
                    start_time=segment.transcript_segment.start_time,
                    end_time=segment.transcript_segment.end_time,
                    visual_type="quote_card",
                    quote_text=key_quote,
                    quote_style="emphasis",
                    animation_type="fade",
                    animation_params={"fade_duration": 0.5},
                ))
                continue
        
        # Default: use related figure or title card
        if segment.referenced_figures:
            figure_id = segment.referenced_figures[0]
            if figure_id in figure_map:
                alignments.append(VisualAssetAlignment(
                    segment_id=segment.segment_id,
                    start_time=segment.transcript_segment.start_time,
                    end_time=segment.transcript_segment.end_time,
                    visual_type="figure",
                    figure_atom_id=figure_id,
                    figure_path=figure_map[figure_id].file_path,
                    animation_type="ken_burns",
                    animation_params={"zoom": 1.1, "pan": "slow_pan"},
                ))
                continue
        
        # Fallback: text card with topic
        alignments.append(VisualAssetAlignment(
            segment_id=segment.segment_id,
            start_time=segment.transcript_segment.start_time,
            end_time=segment.transcript_segment.end_time,
            visual_type="title_card",
            quote_text=segment.key_concepts[0] if segment.key_concepts else "Discussion",
            animation_type="static",
            animation_params={},
        ))
    
    return alignments
```

## 5.2 Timeline Sync QA

```python
@dataclass
class TimelineSyncQA:
    """QA results for timeline synchronization"""
    
    # Overall sync quality
    sync_score: float  # 0-100
    
    # Individual checks
    visual_coverage: float      # % of time with appropriate visual
    figure_timing_accuracy: float  # Do figures appear when mentioned?
    quote_timing_accuracy: float   # Do quotes appear when spoken?
    
    # Issues found
    desync_points: List[DesyncPoint]
    missing_visuals: List[str]  # segment_ids without visuals
    
    passed: bool


@dataclass
class DesyncPoint:
    """A point where visual and audio are out of sync"""
    timestamp: float
    issue: str  # "figure_appears_late", "quote_misaligned", etc.
    expected: str
    actual: str
    severity: str  # "minor", "major"


async def qa_timeline_sync(
    visual_alignments: List[VisualAssetAlignment],
    transcription: TranscriptionResult,
    document_graph: DocumentGraph,
) -> TimelineSyncQA:
    """
    Verify that visuals align correctly with spoken content.
    """
    
    desync_points = []
    
    for alignment in visual_alignments:
        if alignment.visual_type == "figure":
            # Check if figure is mentioned in this segment
            segment_text = get_segment_text(transcription, alignment.start_time, alignment.end_time)
            figure = document_graph.get_atom(alignment.figure_atom_id)
            
            # Look for figure reference in text
            if not mentions_figure(segment_text, figure):
                desync_points.append(DesyncPoint(
                    timestamp=alignment.start_time,
                    issue="figure_not_mentioned",
                    expected=f"Discussion of {figure.figure_number}",
                    actual=segment_text[:100],
                    severity="major",
                ))
        
        elif alignment.visual_type == "quote_card":
            # Check if quote appears in spoken text
            segment_text = get_segment_text(transcription, alignment.start_time, alignment.end_time)
            
            if alignment.quote_text not in segment_text:
                # Check if quote is close (within 5 seconds)
                nearby_text = get_segment_text(
                    transcription, 
                    alignment.start_time - 5, 
                    alignment.end_time + 5
                )
                if alignment.quote_text in nearby_text:
                    desync_points.append(DesyncPoint(
                        timestamp=alignment.start_time,
                        issue="quote_timing_offset",
                        expected="Quote shown when spoken",
                        actual="Quote appears slightly off",
                        severity="minor",
                    ))
                else:
                    desync_points.append(DesyncPoint(
                        timestamp=alignment.start_time,
                        issue="quote_not_found",
                        expected=alignment.quote_text[:50],
                        actual="Not found in nearby audio",
                        severity="major",
                    ))
    
    # Calculate scores
    major_issues = len([d for d in desync_points if d.severity == "major"])
    minor_issues = len([d for d in desync_points if d.severity == "minor"])
    
    sync_score = max(0, 100 - (major_issues * 20) - (minor_issues * 5))
    
    return TimelineSyncQA(
        sync_score=sync_score,
        visual_coverage=calculate_visual_coverage(visual_alignments, transcription.total_duration),
        figure_timing_accuracy=calculate_figure_timing(visual_alignments, transcription),
        quote_timing_accuracy=calculate_quote_timing(visual_alignments, transcription),
        desync_points=desync_points,
        missing_visuals=[],  # TODO: find segments without visuals
        passed=sync_score >= 80,
    )
```

---

# Part 6: CLI Interface

```bash
# === TRAINING DATA MANAGEMENT ===

# Ingest training pairs
claude-studio training ingest \
  --pdf artifacts/training_data/optimal-adversarial-texts-full.pdf \
  --audio artifacts/training_data/optimal-adversarial-texts-full.mp3 \
  --speaker-gender male \
  --source journalclub

# List training pairs
claude-studio training list

# Analyze a training pair
claude-studio training analyze <pair_id>


# === ANALYSIS PHASE ===

# Run full analysis on all pairs
claude-studio training analyze-all

# View extracted profiles
claude-studio training profile show

# View structure patterns
claude-studio training profile structure

# View style patterns  
claude-studio training profile style


# === TRAINING LOOP ===

# Run training with defaults
claude-studio training run

# Run with custom config
claude-studio training run \
  --max-trials 15 \
  --target-depth standard \
  --convergence-threshold 0.03

# Resume training from checkpoint
claude-studio training run --resume


# === MONITORING ===

# View training progress
claude-studio training status

# View specific trial
claude-studio training trial <trial_id>

# Compare trials
claude-studio training compare trial_001 trial_005

# View loss curves
claude-studio training plot-loss


# === EXPORT ===

# Export trained profile for production use
claude-studio training export --output podcast_profile_v1.json

# Export best prompts
claude-studio training export-prompts --output prompts_v1.json
```

---

# Part 7: Memory Schema

```
/org/default/learnings/podcast_training/
├── training_pairs/
│   ├── pair_001/
│   │   ├── metadata.json           # PDF path, audio path, speaker info
│   │   ├── transcription.json      # Full transcription with timestamps
│   │   ├── aligned_segments.json   # Segment analysis
│   │   ├── structure_profile.json
│   │   └── style_profile.json
│   └── pair_002/
│       └── ...
│
├── profiles/
│   ├── aggregated_v1.json          # Combined profile
│   ├── aggregated_v2.json          # After refinement
│   └── current.json                # Symlink to active version
│
├── prompts/
│   ├── v1/
│   │   ├── script_writer.txt
│   │   ├── segment_classifier.txt
│   │   └── quality_judge.txt
│   ├── v2/
│   │   └── ...
│   └── current/                    # Active prompts
│
├── trials/
│   ├── trial_001/
│   │   ├── config.json
│   │   ├── results.json            # All metrics
│   │   ├── pair_001_script.json
│   │   ├── pair_001_audio.mp3
│   │   └── refinement_analysis.json
│   └── trial_002/
│       └── ...
│
└── convergence/
    ├── loss_history.json           # Loss over all trials
    ├── best_trial.json             # Best performing trial
    └── final_report.json           # Training summary
```

---

# Part 8: Implementation Plan

## Phase 1: Training Data Ingestion (Day 1)
- [ ] Add Whisper transcription to pipeline
- [ ] Create TrainingPair model and storage
- [ ] CLI: `training ingest` command
- [ ] Test with one pair

## Phase 2: Analysis Phase (Day 2)
- [ ] Implement segment classification prompt
- [ ] Implement structure profile extraction
- [ ] Implement style profile extraction
- [ ] CLI: `training analyze` command
- [ ] Test with all 4 pairs

## Phase 3: Profile Synthesis (Day 2-3)
- [ ] Implement profile aggregation
- [ ] Store profiles in memory
- [ ] CLI: `training profile` commands

## Phase 4: Loss Metrics (Day 3)
- [ ] Implement duration loss
- [ ] Implement coverage loss
- [ ] Implement structure loss
- [ ] Implement quality loss (LLM judge)
- [ ] Implement ROUGE loss
- [ ] Add rouge-score dependency

## Phase 5: Training Loop (Day 4)
- [ ] Implement main training loop
- [ ] Implement convergence checking
- [ ] Implement prompt refinement
- [ ] CLI: `training run` command
- [ ] Test end-to-end

## Phase 6: Video Calibration (Day 5)
- [ ] Implement visual asset alignment
- [ ] Implement timeline sync QA
- [ ] Integrate with existing video pipeline

## Phase 7: Polish (Day 6)
- [ ] Add training status dashboard
- [ ] Add loss curve plotting
- [ ] Write documentation
- [ ] Final testing

---

# Summary

This spec enables:

1. **Data-driven podcast generation** - Learn from real examples
2. **Measurable quality** - Loss metrics for all aspects
3. **Iterative improvement** - Automated prompt refinement
4. **Configurable depth** - Quick overview to comprehensive
5. **Video integration** - Visual assets aligned to spoken content
6. **Reproducibility** - All versions stored, can rollback/compare
7. **Framework for expansion** - Easy to add more training pairs

The key insight: treat podcast generation like ML training, with clear loss functions, training loops, and convergence criteria.
