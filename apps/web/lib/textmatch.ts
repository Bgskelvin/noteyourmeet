/** Pencocokan kata yang sama persis dengan backend (app/services/corrections.py), untuk hitung pratinjau. */
export function buildMatcher(find: string, opts: { matchCase: boolean; wholeWord: boolean }): RegExp | null {
  const f = find.trim();
  if (!f) return null;
  let body = f.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  if (opts.wholeWord) body = `(?<![\\p{L}\\p{N}_])${body}(?![\\p{L}\\p{N}_])`;
  return new RegExp(body, `gu${opts.matchCase ? "" : "i"}`);
}

export function countMatches(texts: string[], re: RegExp | null): number {
  if (!re) return 0;
  return texts.reduce((n, t) => n + (t.match(re)?.length ?? 0), 0);
}
