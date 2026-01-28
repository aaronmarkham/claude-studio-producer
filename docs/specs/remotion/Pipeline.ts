/**
 * CLAUDE STUDIO PIPELINE: From Knowledge to Synced Video
 * 
 * This file illustrates the data flow and orchestration layer
 * that Claude would manage to produce a data journalism or science explainer video.
 */

// =============================================================================
// PHASE 1: SCRIPT GENERATION
// =============================================================================

/**
 * Claude analyzes the source material (article, paper, dataset) and generates
 * a structured script with "cue markers" for visual elements.
 */

interface ScriptSegment {
  narration: string;
  visualCue?: {
    type: 'chart' | 'diagram' | 'image' | 'broll' | 'equation';
    trigger: string;        // The phrase that triggers this visual
    data?: any;             // Chart data, equation, etc.
    description?: string;   // For AI image generation
  };
}

const GENERATED_SCRIPT: ScriptSegment[] = [
  {
    narration: "According to the latest data, unemployment rose to 7.2 percent in the third quarter.",
    visualCue: {
      type: 'chart',
      trigger: '7.2 percent',
      data: {
        chartType: 'bar',
        values: [
          { label: 'Q1', value: 5.2 },
          { label: 'Q2', value: 5.8 },
          { label: 'Q3', value: 7.2, highlight: true },
        ],
        title: 'Unemployment Rate (%)',
      }
    }
  },
  {
    narration: "This marks the largest quarterly increase since the 2008 financial crisis.",
    visualCue: {
      type: 'chart',
      trigger: '2008 financial crisis',
      data: {
        chartType: 'line',
        values: [/* historical data */],
        annotation: { x: 2008, label: 'Financial Crisis' },
      }
    }
  },
  {
    narration: "Economists attribute this spike to three key factors.",
    visualCue: {
      type: 'diagram',
      trigger: 'three key factors',
      data: {
        type: 'list',
        items: ['Supply chain disruptions', 'Interest rate hikes', 'Consumer sentiment decline'],
      }
    }
  },
];

// =============================================================================
// PHASE 2: TTS + TRANSCRIPTION
// =============================================================================

/**
 * The script is sent to ElevenLabs (or similar) for TTS.
 * We get back:
 *   1. Audio file (MP3/WAV)
 *   2. Word-level timestamps (JSON)
 * 
 * ElevenLabs API: POST /v1/text-to-speech/{voice_id}/with-timestamps
 */

interface TTSResponse {
  audioUrl: string;
  alignment: {
    characters: string[];
    character_start_times_seconds: number[];
    character_end_times_seconds: number[];
  };
}

// Post-processed into word-level timestamps:
interface WordTimestamp {
  word: string;
  start: number;
  end: number;
}

// Example output after processing:
const WORD_TIMESTAMPS: WordTimestamp[] = [
  { word: "According", start: 0.0, end: 0.35 },
  { word: "to", start: 0.35, end: 0.45 },
  // ... etc
  { word: "7.2", start: 2.35, end: 2.8 },
  { word: "percent", start: 2.8, end: 3.3 },
  // ...
];

// =============================================================================
// PHASE 3: CUE POINT EXTRACTION
// =============================================================================

/**
 * Claude matches the visual cue triggers against the transcript
 * to find exact frame numbers for each visual element.
 */

interface VisualCuePoint {
  type: string;
  triggerPhrase: string;
  startFrame: number;
  data: any;
}

function extractCuePoints(
  script: ScriptSegment[],
  timestamps: WordTimestamp[],
  fps: number
): VisualCuePoint[] {
  const cuePoints: VisualCuePoint[] = [];
  
  for (const segment of script) {
    if (!segment.visualCue) continue;
    
    const trigger = segment.visualCue.trigger.toLowerCase();
    
    // Find the word(s) that match the trigger phrase
    for (let i = 0; i < timestamps.length; i++) {
      const window = timestamps.slice(i, i + 3).map(w => w.word.toLowerCase()).join(' ');
      
      if (window.includes(trigger)) {
        const triggerStart = timestamps[i].start;
        cuePoints.push({
          type: segment.visualCue.type,
          triggerPhrase: segment.visualCue.trigger,
          startFrame: Math.round(triggerStart * fps),
          data: segment.visualCue.data,
        });
        break;
      }
    }
  }
  
  return cuePoints;
}

// =============================================================================
// PHASE 4: REMOTION COMPOSITION GENERATION
// =============================================================================

/**
 * Claude generates the actual Remotion code based on the cue points.
 * This is where the magic happens - Claude writes React components
 * that are parameterized by the extracted data.
 */

const GENERATED_COMPOSITION_TEMPLATE = `
import { Composition, Sequence, Audio } from 'remotion';
import { AnimatedBarChart, AnimatedLineChart, BulletList } from './components';

export const GeneratedExplainer = () => {
  return (
    <div className="bg-slate-900 h-full font-sans">
      <Audio src="{AUDIO_URL}" />
      
      {/* Visual cue points are inserted here as Sequences */}
      {CUE_POINTS.map(cue => (
        <Sequence key={cue.triggerPhrase} from={cue.startFrame - ANTICIPATION_FRAMES}>
          {renderVisualForCue(cue)}
        </Sequence>
      ))}
      
      <AnimatedCaption transcript={TRANSCRIPT} />
    </div>
  );
};

function renderVisualForCue(cue: VisualCuePoint) {
  switch (cue.type) {
    case 'chart':
      if (cue.data.chartType === 'bar') {
        return <AnimatedBarChart data={cue.data.values} />;
      }
      if (cue.data.chartType === 'line') {
        return <AnimatedLineChart data={cue.data.values} />;
      }
      break;
    case 'diagram':
      return <BulletList items={cue.data.items} />;
    // ... etc
  }
}
`;

// =============================================================================
// PHASE 5: COMPOSITION CONFIG
// =============================================================================

/**
 * The final piece: compute total duration from audio and register the composition.
 */

interface CompositionConfig {
  id: string;
  durationInFrames: number;
  fps: number;
  width: number;
  height: number;
  defaultProps: {
    audioUrl: string;
    transcript: WordTimestamp[];
    cuePoints: VisualCuePoint[];
  };
}

function generateCompositionConfig(
  audioUrl: string,
  audioDurationSeconds: number,
  transcript: WordTimestamp[],
  cuePoints: VisualCuePoint[],
  fps: number = 30
): CompositionConfig {
  return {
    id: 'DataJournalismExplainer',
    durationInFrames: Math.ceil(audioDurationSeconds * fps) + fps, // +1 second padding
    fps,
    width: 1920,
    height: 1080,
    defaultProps: {
      audioUrl,
      transcript,
      cuePoints,
    },
  };
}

// =============================================================================
// THE FULL PIPELINE (What Claude Orchestrates)
// =============================================================================

async function claudeStudioPipeline(sourceContent: string) {
  // Step 1: Analyze source and generate script with visual cues
  const script = await claude.generateScript(sourceContent);
  
  // Step 2: Concatenate narration and send to TTS
  const fullNarration = script.map(s => s.narration).join(' ');
  const ttsResponse = await elevenlabs.generateWithTimestamps(fullNarration);
  
  // Step 3: Process timestamps into word-level format
  const wordTimestamps = processTimestamps(ttsResponse.alignment);
  
  // Step 4: Extract cue points by matching triggers to timestamps
  const cuePoints = extractCuePoints(script, wordTimestamps, 30);
  
  // Step 5: Generate Remotion composition code
  const compositionCode = await claude.generateRemotionCode({
    script,
    wordTimestamps,
    cuePoints,
    audioUrl: ttsResponse.audioUrl,
  });
  
  // Step 6: Write files to project
  await fs.writeFile('src/compositions/explainer/index.tsx', compositionCode);
  await fs.writeFile('src/compositions/explainer/transcript.json', JSON.stringify(wordTimestamps));
  
  // Step 7: Render
  await exec('npx remotion render DataJournalismExplainer out/explainer.mp4');
  
  return {
    videoPath: 'out/explainer.mp4',
    cuePoints,
    transcript: wordTimestamps,
  };
}

// =============================================================================
// EXAMPLE: SCIENCE PAPER EXPLAINER VARIANT
// =============================================================================

/**
 * For science papers, we'd extend this with:
 * - Figure extraction from PDF
 * - Equation rendering (KaTeX/MathJax in React)
 * - Citation callouts
 * - Methodology diagrams (Mermaid/D2)
 */

interface SciencePaperScript extends ScriptSegment {
  visualCue?: {
    type: 'chart' | 'diagram' | 'equation' | 'figure' | 'citation';
    trigger: string;
    data?: any;
    figureRef?: string;      // Reference to extracted figure
    equation?: string;       // LaTeX string
    citationKey?: string;    // For highlighting citations
  };
}

const SCIENCE_PAPER_EXAMPLE: SciencePaperScript[] = [
  {
    narration: "The researchers found that the treatment reduced mortality by 34 percent.",
    visualCue: {
      type: 'chart',
      trigger: '34 percent',
      data: {
        chartType: 'bar',
        values: [
          { label: 'Control', value: 100 },
          { label: 'Treatment', value: 66, highlight: true },
        ],
        title: 'Relative Mortality Rate',
      }
    }
  },
  {
    narration: "This effect followed a clear dose-response relationship, as shown in Figure 2.",
    visualCue: {
      type: 'figure',
      trigger: 'Figure 2',
      figureRef: 'figures/fig2_dose_response.png',  // Extracted from PDF
    }
  },
  {
    narration: "The underlying mechanism can be expressed by the equation...",
    visualCue: {
      type: 'equation',
      trigger: 'equation',
      equation: 'E = mc^2',  // Would be actual paper equation
    }
  },
];

export {
  ScriptSegment,
  WordTimestamp,
  VisualCuePoint,
  extractCuePoints,
  generateCompositionConfig,
  claudeStudioPipeline,
};
