import { describe, expect, it } from 'vitest';
import { initialTypewriterState, TYPEWRITER_TIMING, typewriterStep, type TypewriterState } from './typewriter';

const WORDS = ['ab', 'xyz'];

// Run the machine until the predicate holds, collecting every frame's text.
function runUntil(words: string[], done: (s: TypewriterState) => boolean, reduce = false) {
  let state = initialTypewriterState(words);
  const frames: string[] = [];
  for (let i = 0; i < 100 && !done(state); i++) {
    state = typewriterStep(words, state, reduce).state;
    frames.push(state.text);
  }
  return { state, frames };
}

describe('initialTypewriterState', () => {
  // The first word is on screen before any animation runs.
  it('starts on the first word, ready to delete it', () => {
    expect(initialTypewriterState(WORDS)).toEqual({ index: 0, text: 'ab', deleting: true });
  });

  // No words means an empty slot.
  it('starts empty for an empty list', () => {
    expect(initialTypewriterState([]).text).toBe('');
  });
});

describe('typewriterStep', () => {
  // The word is deleted a letter at a time, then the next word is typed in.
  it('deletes the current word then types the next one letter by letter', () => {
    const { frames } = runUntil(WORDS, (s) => s.index === 1 && s.text === 'xyz');
    expect(frames).toEqual(['a', '', '', 'x', 'xy', 'xyz']);
  });

  // A fully typed word is held before deleting starts again.
  it('holds a finished word before deleting it', () => {
    const typed: TypewriterState = { index: 1, text: 'xyz', deleting: false };
    const step = typewriterStep(WORDS, typed);
    expect(step.state.deleting).toBe(true);
    expect(step.state.text).toBe('xyz');
    expect(step.delayMs).toBe(TYPEWRITER_TIMING.holdMs);
  });

  // After the last word it wraps back to the first.
  it('wraps around to the first word', () => {
    const lastEmpty: TypewriterState = { index: 1, text: '', deleting: true };
    expect(typewriterStep(WORDS, lastEmpty).state).toEqual({ index: 0, text: '', deleting: false });
  });

  // Reduced motion swaps whole words on a slow cadence, no typing frames.
  it('swaps whole words under reduced motion', () => {
    const step = typewriterStep(WORDS, initialTypewriterState(WORDS), true);
    expect(step.state.text).toBe('xyz');
    expect(step.delayMs).toBe(TYPEWRITER_TIMING.reducedMotionMs);
    expect(typewriterStep(WORDS, step.state, true).state.text).toBe('ab');
  });

  // Each phase uses its own speed.
  it('uses the delete, type, and between-word delays', () => {
    expect(typewriterStep(WORDS, { index: 0, text: 'ab', deleting: true }).delayMs).toBe(TYPEWRITER_TIMING.deleteMs);
    expect(typewriterStep(WORDS, { index: 0, text: '', deleting: true }).delayMs).toBe(TYPEWRITER_TIMING.betweenWordsMs);
    expect(typewriterStep(WORDS, { index: 1, text: 'x', deleting: false }).delayMs).toBe(TYPEWRITER_TIMING.typeMs);
  });

  // An empty word list leaves the state alone instead of throwing.
  it('is a no-op for an empty list', () => {
    const state = initialTypewriterState([]);
    expect(typewriterStep([], state).state).toBe(state);
  });
});
