// Parse the hero's rotating mission words from the `missionWords` setting: one
// word per line, trimmed, blank lines dropped. Falls back to "people" so the
// typewriter always has something to show.
export const DEFAULT_MISSION_WORD = 'people';

export function parseMissionWords(raw: string | undefined | null): string[] {
  const words = (raw ?? '')
    .split(/\r?\n/)
    .map((w) => w.trim())
    .filter((w) => w.length > 0);
  return words.length > 0 ? words : [DEFAULT_MISSION_WORD];
}

/** The longest word, used to size the typewriter slot so nothing shifts. */
export function longestWord(words: string[]): string {
  return words.reduce((a, b) => (b.length > a.length ? b : a), '');
}

/** Screen-reader list: "a, b, and c". */
export function listForReaders(words: string[]): string {
  if (words.length <= 1) return words.join('');
  if (words.length === 2) return `${words[0]} and ${words[1]}`;
  return `${words.slice(0, -1).join(', ')}, and ${words[words.length - 1]}`;
}
