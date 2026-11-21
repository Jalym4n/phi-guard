/**
 * Convert the browser's text selection inside a container into string offsets
 * (UTF-16 units) of the underlying document text.  Text inside elements marked
 * `data-skip` (the small type labels shown inside highlights) is not part of
 * the document and is not counted.
 */
function isSkipped(node: Node): boolean {
  return Boolean(node.parentElement?.closest("[data-skip]"));
}

function textNodes(container: Node): Text[] {
  const out: Text[] = [];
  const walker = document.createTreeWalker(container, NodeFilter.SHOW_TEXT);
  for (let n = walker.nextNode(); n; n = walker.nextNode()) out.push(n as Text);
  return out;
}

export function offsetIn(container: Node, node: Node, nodeOffset: number): number {
  const nodes = textNodes(container);
  let total = 0;
  if (node.nodeType === Node.TEXT_NODE) {
    for (const t of nodes) {
      if (t === node) return total + (isSkipped(t) ? 0 : nodeOffset);
      if (!isSkipped(t)) total += t.length;
    }
    return total;
  }
  // An element boundary: count every text node that comes before child #nodeOffset.
  const boundary = node.childNodes[nodeOffset] ?? null;
  for (const t of nodes) {
    const before = boundary
      ? Boolean(boundary.compareDocumentPosition(t) & Node.DOCUMENT_POSITION_PRECEDING) && !boundary.contains(t)
      : node.contains(t) || Boolean(node.compareDocumentPosition(t) & Node.DOCUMENT_POSITION_PRECEDING);
    if (before && !isSkipped(t)) total += t.length;
  }
  return total;
}

export function selectionOffsets(container: HTMLElement): { start: number; end: number } | null {
  const sel = window.getSelection();
  if (!sel || sel.rangeCount === 0 || sel.isCollapsed) return null;
  const range = sel.getRangeAt(0);
  if (!container.contains(range.startContainer) || !container.contains(range.endContainer)) return null;
  const a = offsetIn(container, range.startContainer, range.startOffset);
  const b = offsetIn(container, range.endContainer, range.endOffset);
  const start = Math.min(a, b);
  const end = Math.max(a, b);
  return end > start ? { start, end } : null;
}

/** Trim whitespace from both ends of a span so "  Lakeview " becomes "Lakeview". */
export function trimSpan(text: string, start: number, end: number): { start: number; end: number } {
  while (start < end && /\s/.test(text[start] ?? "")) start++;
  while (end > start && /\s/.test(text[end - 1] ?? "")) end--;
  return { start, end };
}

/** Every exact occurrence of `needle` in `text`, for "Add a word or phrase". */
export function findAll(text: string, needle: string): { start: number; end: number }[] {
  const out: { start: number; end: number }[] = [];
  if (!needle) return out;
  for (let i = text.indexOf(needle); i !== -1; i = text.indexOf(needle, i + needle.length)) {
    out.push({ start: i, end: i + needle.length });
  }
  return out;
}
