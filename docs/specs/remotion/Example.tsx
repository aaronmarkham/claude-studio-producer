/**
 * REMOTION EXAMPLE: Syncing Chart Animation to Narration
 * 
 * This demonstrates the core pattern for "when we mention a stat, show the chart"
 * 
 * The key insight: TTS services like ElevenLabs return word-level timestamps.
 * We use these to trigger visual elements at the exact right moment.
 */

import { useCurrentFrame, useVideoConfig, Audio, Sequence, interpolate, spring } from 'remotion';

// =============================================================================
// 1. TRANSCRIPT DATA STRUCTURE
// =============================================================================
// This is what you get back from ElevenLabs or Deepgram after TTS generation
// Each word has start/end times in seconds

interface TranscriptWord {
  word: string;
  start: number;  // seconds
  end: number;    // seconds
}

const TRANSCRIPT: TranscriptWord[] = [
  { word: "According", start: 0.0, end: 0.35 },
  { word: "to", start: 0.35, end: 0.45 },
  { word: "the", start: 0.45, end: 0.55 },
  { word: "latest", start: 0.55, end: 0.85 },
  { word: "data,", start: 0.85, end: 1.2 },
  { word: "unemployment", start: 1.3, end: 1.95 },
  { word: "rose", start: 1.95, end: 2.2 },
  { word: "to", start: 2.2, end: 2.35 },
  { word: "7.2", start: 2.35, end: 2.8 },        // <-- THIS IS OUR TRIGGER POINT
  { word: "percent", start: 2.8, end: 3.3 },
  { word: "in", start: 3.4, end: 3.5 },
  { word: "the", start: 3.5, end: 3.6 },
  { word: "third", start: 3.6, end: 3.85 },
  { word: "quarter.", start: 3.85, end: 4.4 },
];

// =============================================================================
// 2. HELPER: Convert seconds to frames
// =============================================================================

function secondsToFrames(seconds: number, fps: number): number {
  return Math.round(seconds * fps);
}

// Helper to find when a specific phrase starts in the transcript
function findPhraseStart(transcript: TranscriptWord[], phrase: string): number {
  const word = transcript.find(w => w.word.includes(phrase));
  return word ? word.start : 0;
}

// =============================================================================
// 3. ANIMATED BAR CHART COMPONENT
// =============================================================================

interface BarChartProps {
  data: { label: string; value: number; highlight?: boolean }[];
  animationStart: number; // frame to start animating
}

const AnimatedBarChart: React.FC<BarChartProps> = ({ data, animationStart }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  
  const maxValue = Math.max(...data.map(d => d.value));
  const STAGGER_DELAY = 5; // frames between each bar starting
  
  return (
    <div style={{
      display: 'flex',
      alignItems: 'flex-end',
      justifyContent: 'center',
      gap: 24,
      height: 300,
      padding: 40,
    }}>
      {data.map((item, index) => {
        // Each bar starts animating at a staggered time
        const barDelay = animationStart + (index * STAGGER_DELAY);
        
        // Spring animation for smooth easing
        const progress = spring({
          frame: frame - barDelay,
          fps,
          config: {
            damping: 20,
            stiffness: 100,
          },
        });
        
        // Clamp progress between 0 and 1
        const clampedProgress = Math.max(0, Math.min(1, progress));
        const barHeight = clampedProgress * (item.value / maxValue) * 200;
        
        return (
          <div key={item.label} style={{ textAlign: 'center' }}>
            {/* The bar */}
            <div
              style={{
                width: 60,
                height: barHeight,
                backgroundColor: item.highlight ? '#ef4444' : '#3b82f6',
                borderRadius: '4px 4px 0 0',
                transition: 'background-color 0.3s',
              }}
            />
            {/* Value label - fades in after bar grows */}
            <div style={{
              marginTop: 8,
              fontSize: 18,
              fontWeight: 'bold',
              color: item.highlight ? '#ef4444' : '#fff',
              opacity: interpolate(
                frame - barDelay - 15,
                [0, 10],
                [0, 1],
                { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' }
              ),
            }}>
              {item.value}%
            </div>
            {/* Label */}
            <div style={{
              marginTop: 4,
              fontSize: 14,
              color: '#94a3b8',
            }}>
              {item.label}
            </div>
          </div>
        );
      })}
    </div>
  );
};

// =============================================================================
// 4. CAPTION/SUBTITLE COMPONENT
// =============================================================================

interface CaptionProps {
  transcript: TranscriptWord[];
  highlightPhrase?: string;
}

const AnimatedCaption: React.FC<CaptionProps> = ({ transcript, highlightPhrase }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const currentTime = frame / fps;
  
  // Find which words should be visible/highlighted at current time
  const visibleWords = transcript.filter(w => w.start <= currentTime);
  const currentWord = transcript.find(w => w.start <= currentTime && w.end >= currentTime);
  
  return (
    <div style={{
      position: 'absolute',
      bottom: 80,
      left: 0,
      right: 0,
      textAlign: 'center',
      fontSize: 32,
      color: '#fff',
      textShadow: '2px 2px 4px rgba(0,0,0,0.8)',
    }}>
      {visibleWords.slice(-8).map((word, i) => {  // Show last 8 words
        const isCurrentWord = word === currentWord;
        const isHighlighted = highlightPhrase && word.word.includes(highlightPhrase);
        
        return (
          <span
            key={`${word.word}-${word.start}`}
            style={{
              color: isHighlighted ? '#ef4444' : isCurrentWord ? '#fbbf24' : '#fff',
              fontWeight: isHighlighted || isCurrentWord ? 'bold' : 'normal',
              marginRight: 8,
            }}
          >
            {word.word}
          </span>
        );
      })}
    </div>
  );
};

// =============================================================================
// 5. MAIN COMPOSITION
// =============================================================================

export const StatMentionExample: React.FC = () => {
  const { fps } = useVideoConfig();
  
  // Find exactly when "7.2" is spoken
  const statMentionTime = findPhraseStart(TRANSCRIPT, '7.2');
  const chartTriggerFrame = secondsToFrames(statMentionTime, fps);
  
  // Unemployment data for the chart
  const unemploymentData = [
    { label: 'Q1', value: 5.2 },
    { label: 'Q2', value: 5.8 },
    { label: 'Q3', value: 7.2, highlight: true },  // The stat we're mentioning
  ];
  
  return (
    <div style={{
      flex: 1,
      backgroundColor: '#0f172a',
      fontFamily: 'Inter, system-ui, sans-serif',
    }}>
      {/* Audio track */}
      <Audio src="/audio/narration.mp3" />
      
      {/* Title - always visible */}
      <div style={{
        position: 'absolute',
        top: 40,
        left: 0,
        right: 0,
        textAlign: 'center',
        fontSize: 24,
        color: '#94a3b8',
        textTransform: 'uppercase',
        letterSpacing: 2,
      }}>
        Quarterly Unemployment Report
      </div>
      
      {/* Chart appears when the stat is mentioned */}
      <Sequence from={chartTriggerFrame - 15} layout="none">
        {/* Start 15 frames (~0.5s) early for anticipation */}
        <div style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          height: '100%',
        }}>
          <AnimatedBarChart 
            data={unemploymentData} 
            animationStart={15}  // Relative to sequence start
          />
        </div>
      </Sequence>
      
      {/* Captions synced to audio */}
      <AnimatedCaption 
        transcript={TRANSCRIPT} 
        highlightPhrase="7.2"
      />
    </div>
  );
};

// =============================================================================
// 6. COMPOSITION CONFIG (for Root.tsx)
// =============================================================================

export const StatMentionExampleConfig = {
  id: 'StatMentionExample',
  component: StatMentionExample,
  durationInFrames: 30 * 6,  // 6 seconds at 30fps
  fps: 30,
  width: 1920,
  height: 1080,
};
