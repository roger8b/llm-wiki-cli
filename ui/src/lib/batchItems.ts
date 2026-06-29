/** Collapse a long batch list into the first N items plus a hidden count.
 *
 *  With bulk operations (e.g. ingesting 50 pending sources at once) the
 *  per-item progress list can become a wall of rows. The UI renders the
 *  visible slice + a "...and N more. See Jobs" link instead. (#339)
 */
export function truncateBatchItems<T>(
  items: T[],
  limit: number,
): { visible: T[]; hiddenCount: number } {
  if (items.length <= limit) return { visible: items, hiddenCount: 0 }
  return { visible: items.slice(0, limit), hiddenCount: items.length - limit }
}