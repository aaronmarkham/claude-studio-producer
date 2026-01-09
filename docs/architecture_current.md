```mermaid
flowchart TB
    subgraph Input["📥 Input"]
        Request["Production Request<br/>concept + budget + seed assets"]
    end

    subgraph Memory["🧠 Custom Memory System"]
        STM["Short-Term Memory<br/>Run state, progress, assets"]
        LTM["Long-Term Memory<br/>Patterns, preferences,<br/>provider learnings"]
    end

    subgraph Planning["🎯 Planning Stage"]
        Producer["🤖 ProducerAgent<br/>Creates pilot strategies"]
        ScriptWriter["📝 ScriptWriterAgent<br/>Generates scenes"]
    end

    subgraph Generation["⚡ Parallel Generation (Strands)"]
        Video["🎬 VideoGenerator<br/>Luma / Runway"]
        Audio["🎤 AudioGenerator<br/>OpenAI TTS"]
    end

    subgraph Evaluation["🔍 Real Evaluation Pipeline"]
        QA["✅ QAVerifier<br/>Claude Vision<br/>Frame extraction + analysis"]
        Critic["⭐ CriticAgent<br/>Scores + decisions +<br/>provider analysis"]
    end

    subgraph Output["📤 Output Stage"]
        Editor["✂️ EditorAgent<br/>Edit candidates"]
        Renderer["🎥 FFmpegRenderer<br/>Final video + text overlays"]
    end

    %% Main flow
    Request --> Producer
    Producer --> ScriptWriter
    ScriptWriter --> Video
    ScriptWriter --> Audio
    Video --> QA
    Audio --> QA
    QA --> Critic
    Critic --> Editor
    Editor --> Renderer

    %% Memory reads (blue dashed)
    LTM -.->|"provider guidelines<br/>patterns"| Producer
    LTM -.->|"prompt tips<br/>avoid list"| ScriptWriter
    STM -.->|"run state"| QA

    %% Memory writes (red dashed)
    Producer -.->|"pilots"| STM
    Video -.->|"assets"| STM
    Critic -.->|"⭐ provider learnings<br/>what worked/failed"| LTM
    Renderer -.->|"completion"| LTM

    %% Styling
    style Input fill:#1a1a2e,stroke:#4a9eff,color:#fff
    style Memory fill:#2d1b4e,stroke:#e74c3c,color:#fff
    style Planning fill:#16213e,stroke:#4a9eff,color:#fff
    style Generation fill:#1a1a2e,stroke:#f39c12,color:#fff
    style Evaluation fill:#16213e,stroke:#2ecc71,color:#fff
    style Output fill:#1a1a2e,stroke:#9b59b6,color:#fff

    style LTM fill:#4a1a4a,stroke:#e74c3c,color:#fff
    style STM fill:#4a1a4a,stroke:#f39c12,color:#fff
    style Critic fill:#1e4a1e,stroke:#2ecc71,color:#fff
```

## Current State: Custom Memory System

### What We Have Now ✅

**Short-Term Memory (per run)**
- Run state and progress tracking
- Pilot decisions and scores
- Generated assets (videos, audio)
- Timeline of events
- Stored in `artifacts/runs/{id}/memory.json`

**Long-Term Memory (persists forever)**
- User preferences (style, voice, quality threshold)
- Production history (past runs, scores, costs)
- Learned patterns (intro → ANIMATED tier works well)
- **Provider Knowledge** ⭐ NEW
  - What worked: "Detailed physical descriptions"
  - What failed: "VFX transformations, magical effects"
  - Prompt tips: "Keep prompts concise, focus on photorealistic"
  - Avoid list: "Complex multi-stage effects"
- Stored in `artifacts/memory/long_term.json`

### The Learning Loop 🔄

```
1. Run starts
   ↓
2. Producer checks LTM for provider guidelines
   ↓
3. ScriptWriter uses guidelines to craft better prompts
   ↓
4. Video generated
   ↓
5. QA Verifier extracts frames, Claude Vision analyzes
   ↓
6. Critic evaluates AND analyzes provider performance
   ↓
7. Learnings written to LTM
   ↓
8. Next run benefits from learnings!
```

### Limitations

- Custom JSON file storage (not scalable)
- No semantic search over memories
- Manual serialization/deserialization
- Not integrated with Strands framework
- No conversation memory between sessions
