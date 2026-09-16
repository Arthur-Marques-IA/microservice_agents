export interface DiffLine {
  type: "same" | "added" | "removed";
  text: string;
}

/** Diff linha a linha (LCS) — as instruções são listas curtas, O(n·m) é suficiente. */
export function diffLines(from: string[], to: string[]): DiffLine[] {
  const m = from.length;
  const n = to.length;
  const lcs = Array.from({ length: m + 1 }, () => new Array<number>(n + 1).fill(0));
  for (let i = m - 1; i >= 0; i--) {
    for (let j = n - 1; j >= 0; j--) {
      lcs[i][j] = from[i] === to[j] ? lcs[i + 1][j + 1] + 1 : Math.max(lcs[i + 1][j], lcs[i][j + 1]);
    }
  }

  const result: DiffLine[] = [];
  let i = 0;
  let j = 0;
  while (i < m && j < n) {
    if (from[i] === to[j]) {
      result.push({ type: "same", text: from[i] });
      i++;
      j++;
    } else if (lcs[i + 1][j] >= lcs[i][j + 1]) {
      result.push({ type: "removed", text: from[i++] });
    } else {
      result.push({ type: "added", text: to[j++] });
    }
  }
  while (i < m) result.push({ type: "removed", text: from[i++] });
  while (j < n) result.push({ type: "added", text: to[j++] });
  return result;
}
