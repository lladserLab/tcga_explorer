import { getGlossaryTerm, getHelpEntry, helpProse } from "./registry";

/**
 * `t(id)` returns flattened prose for one or more help entries. `t.entry`,
 * `t.term`, `t.caption` and `t.glossary` expose the structured forms.
 *
 * Help copy is English only, so this resolver is a stable singleton rather than
 * a context: there is no language to propagate.
 */
function createHelpText() {
  const resolve = (entryIds) => helpProse(entryIds);
  resolve.entry = (entryId) => getHelpEntry(entryId);
  resolve.term = (entryId) => getHelpEntry(entryId).term;
  // Compact one-line label for dense option grids, falling back to the term.
  resolve.caption = (entryId) => {
    const record = getHelpEntry(entryId);
    return record.caption || record.term;
  };
  resolve.glossary = (conceptId) => getGlossaryTerm(conceptId);
  return Object.freeze(resolve);
}

export const helpText = createHelpText();

export function useHelpText() {
  return helpText;
}
