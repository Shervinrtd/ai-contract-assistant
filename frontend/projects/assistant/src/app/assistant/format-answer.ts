/**
 * Turns the assistant's Markdown-ish answer into a small block/inline model that the
 * template renders with normal bindings, so no HTML from the model is ever injected.
 * Supported: paragraphs, "- " / "1. " lists, **bold**, _italic_ and [n] citation markers.
 */

export type Inline =
  | { kind: 'text'; text: string }
  | { kind: 'bold'; text: string }
  | { kind: 'italic'; text: string }
  | { kind: 'cite'; n: number };

export type Block = { kind: 'paragraph'; content: Inline[] } | { kind: 'list'; items: Inline[][] };

const INLINE = /(\*\*[^*]+\*\*|__[^_]+__|(?<![\w])_[^_\n]+_(?![\w])|\[\d+\])/g;
const LIST_ITEM = /^\s*(?:[-*•]|\d+[.)])\s+(.*)$/;

export function parseInline(text: string): Inline[] {
  const out: Inline[] = [];
  let last = 0;
  for (const match of text.matchAll(INLINE)) {
    const token = match[0];
    const index = match.index ?? 0;
    if (index > last) out.push({ kind: 'text', text: text.slice(last, index) });
    if (token.startsWith('[')) out.push({ kind: 'cite', n: Number(token.slice(1, -1)) });
    else if (token.startsWith('**') || token.startsWith('__')) out.push({ kind: 'bold', text: token.slice(2, -2) });
    else out.push({ kind: 'italic', text: token.slice(1, -1) });
    last = index + token.length;
  }
  if (last < text.length) out.push({ kind: 'text', text: text.slice(last) });
  return out;
}

export function formatAnswer(answer: string): Block[] {
  const blocks: Block[] = [];
  let paragraph: string[] = [];
  let list: Inline[][] | null = null;

  const flushParagraph = () => {
    if (paragraph.length) blocks.push({ kind: 'paragraph', content: parseInline(paragraph.join(' ')) });
    paragraph = [];
  };
  const flushList = () => {
    if (list?.length) blocks.push({ kind: 'list', items: list });
    list = null;
  };

  for (const raw of answer.split('\n')) {
    const line = raw.trimEnd();
    const item = LIST_ITEM.exec(line);
    if (item) {
      flushParagraph();
      (list ??= []).push(parseInline(item[1]));
    } else if (!line.trim()) {
      flushParagraph();
      flushList();
    } else {
      flushList();
      paragraph.push(line.trim());
    }
  }
  flushParagraph();
  flushList();
  return blocks;
}
