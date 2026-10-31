export function median(nums) {
  if (!nums?.length) return null;
  const sorted = [...nums].sort((a, b) => a - b);
  return +((sorted[Math.floor((sorted.length - 1) / 2)] + sorted[Math.floor(sorted.length / 2)]) / 2).toFixed(2);
}
export function recallAtK(ids, relevant, k = 3) {
  if (!relevant.length) return 0;
  return ids.slice(0, k).filter(id => relevant.includes(id)).length / relevant.length;
}
export function ndcgAtK(ids, relevant, k = 3) {
  const gains = ids.slice(0, k).map((id, i) => relevant.includes(id) ? 1 / Math.log2(i + 2) : 0);
  const ideal = Array(Math.min(k, relevant.length)).fill(0).reduce((s, _, i) => s + 1 / Math.log2(i + 2), 0);
  return ideal ? gains.reduce((a, b) => a + b, 0) / ideal : 0;
}
export function mean(nums) { return nums.length ? +(nums.reduce((a,b) => a+b, 0) / nums.length).toFixed(4) : null; }
