// The hero's rotating-word animation as a pure state machine. Each step
// returns the text to show and how long to wait before the next step; the
// component's script just applies it on a timer. With reduced motion it swaps
// whole words instead of typing.
export interface TypewriterState {
  /** Index of the word currently being shown, typed, or deleted. */
  index: number;
  /** The text currently on screen. */
  text: string;
  /** True while deleting the current word. */
  deleting: boolean;
}

export interface TypewriterStep {
  state: TypewriterState;
  delayMs: number;
}

export const TYPEWRITER_TIMING = {
  firstDelayMs: 2000,
  deleteMs: 45,
  typeMs: 90,
  betweenWordsMs: 300,
  holdMs: 1900,
  reducedMotionMs: 2600,
} as const;

export function initialTypewriterState(words: readonly string[]): TypewriterState {
  return { index: 0, text: words[0] ?? '', deleting: true };
}

export function typewriterStep(
  words: readonly string[],
  state: TypewriterState,
  reduceMotion = false,
): TypewriterStep {
  const t = TYPEWRITER_TIMING;
  if (words.length === 0) return { state, delayMs: t.holdMs };
  if (reduceMotion) {
    const index = (state.index + 1) % words.length;
    return { state: { index, text: words[index], deleting: true }, delayMs: t.reducedMotionMs };
  }
  const word = words[state.index] ?? '';
  if (state.deleting) {
    if (state.text.length > 0) {
      return { state: { ...state, text: state.text.slice(0, -1) }, delayMs: t.deleteMs };
    }
    const index = (state.index + 1) % words.length;
    return { state: { index, text: '', deleting: false }, delayMs: t.betweenWordsMs };
  }
  if (state.text.length < word.length) {
    return { state: { ...state, text: word.slice(0, state.text.length + 1) }, delayMs: t.typeMs };
  }
  return { state: { ...state, deleting: true }, delayMs: t.holdMs };
}
