// The home Technology section shows at most three tools; an empty result means
// the section is hidden.
export const MAX_HOME_TOOLS = 3;

export function visibleTools<T>(tools: readonly T[], max: number = MAX_HOME_TOOLS): T[] {
  return tools.slice(0, Math.max(0, max));
}
