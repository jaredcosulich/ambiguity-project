import { describe, expect, it } from 'vitest';
import { DEFAULT_MISSION_WORD, listForReaders, longestWord, parseMissionWords } from './missionWords';

describe('parseMissionWords', () => {
  // One word per line, as the CMS textarea stores it.
  it('splits the setting into one word per line', () => {
    expect(parseMissionWords('people\nstudents\nschools')).toEqual(['people', 'students', 'schools']);
  });

  // Stray spaces and Windows line endings are cleaned up.
  it('trims whitespace and handles CRLF line endings', () => {
    expect(parseMissionWords('  people \r\n students\r\n')).toEqual(['people', 'students']);
  });

  // Blank lines left by an editor are ignored.
  it('drops blank lines', () => {
    expect(parseMissionWords('people\n\n   \nschools')).toEqual(['people', 'schools']);
  });

  // An empty or missing setting still gives the typewriter a word.
  it('falls back to people when empty or missing', () => {
    expect(parseMissionWords('')).toEqual([DEFAULT_MISSION_WORD]);
    expect(parseMissionWords('  \n ')).toEqual(['people']);
    expect(parseMissionWords(undefined)).toEqual(['people']);
    expect(parseMissionWords(null)).toEqual(['people']);
  });
});

describe('longestWord', () => {
  // The slot is sized to the longest word so nothing shifts as words change.
  it('returns the longest word', () => {
    expect(longestWord(['people', 'organizations', 'schools'])).toBe('organizations');
  });

  // On a tie the first longest word wins.
  it('keeps the first word on a tie', () => {
    expect(longestWord(['abc', 'xyz'])).toBe('abc');
  });

  // An empty list measures as an empty string.
  it('returns an empty string for no words', () => {
    expect(longestWord([])).toBe('');
  });
});

describe('listForReaders', () => {
  // Screen readers hear the full list with an Oxford comma.
  it('joins three or more words with commas and and', () => {
    expect(listForReaders(['people', 'students', 'schools'])).toBe('people, students, and schools');
  });

  // Two words read as a simple pair.
  it('joins two words with and', () => {
    expect(listForReaders(['people', 'schools'])).toBe('people and schools');
  });

  // A single word or none reads as-is.
  it('returns a lone word unchanged and an empty list as empty', () => {
    expect(listForReaders(['people'])).toBe('people');
    expect(listForReaders([])).toBe('');
  });
});
