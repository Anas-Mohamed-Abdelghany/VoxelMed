import React from 'react';

// ---------------------------------------------------------------------------
// Grounded Organ Badges
// Turns organ mentions inside AI report text into clickable badges that call
// navigateToLandmark(organ). Only organs with a REAL centroid from
// segmentation (landmarkPositions) become badges — so the UI can never claim
// grounding it doesn't have.
// ---------------------------------------------------------------------------

const normName = (s) => String(s).toLowerCase().replace(/[\s_-]+/g, ' ').trim();
const escapeRe = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

export function buildOrganMatcher(landmarkPositions = {}) {
  const entries = Object.entries(landmarkPositions).filter(
    ([, pos]) => Array.isArray(pos) && pos.length >= 3
  );
  if (entries.length === 0) return null;

  const byName = new Map();
  const patterns = [];

  for (const [key, pos] of entries) {
    const label = key.replace(/[_\s]+/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
    const entry = { key, label, pos };
    byName.set(normName(key), entry);
    byName.set(normName(label), entry);

    // "kidneys" -> "kidney(?:s)?" so both singular and plural mentions match
    const stem = key.replace(/s$/i, '');
    patterns.push(`${escapeRe(stem).replace(/[_\s-]+/g, '[\\s_-]+')}(?:s)?`);
  }

  // Longest pattern first so "gluteus maximus" wins over shorter overlaps
  patterns.sort((a, b) => b.length - a.length);

  const source = `(^|[^A-Za-z0-9])(${patterns.join('|')})(?![A-Za-z0-9])`;
  return { source, byName };
}

function OrganBadge({ entry, onNavigate }) {
  return (
    <button
      type="button"
      onClick={(e) => {
        e.preventDefault();
        e.stopPropagation();
        onNavigate?.(entry.key);
      }}
      title={`Grounded landmark — jump to ${entry.label} (centroid slices ${entry.pos.join(', ')})`}
      className="mx-0.5 inline-flex select-none items-center gap-1 rounded-full border border-amber-400/40 bg-amber-400/10 px-1.5 py-[1px] align-middle text-[10px] font-semibold leading-tight text-amber-300 transition-colors hover:border-amber-300 hover:bg-amber-400/25 hover:text-amber-200"
    >
      <span className="h-1 w-1 rounded-full bg-amber-400" />
      {entry.label}
    </button>
  );
}

function splitText(text, matcher, onNavigate) {
  if (typeof text !== 'string' || text.length < 3) return text;

  const re = new RegExp(matcher.source, 'gi');
  const out = [];
  let last = 0;
  let m;

  while ((m = re.exec(text)) !== null) {
    const prefix = m[1] || '';
    const start = m.index + prefix.length;
    const matched = m[2];
    if (start > last) out.push(text.slice(last, start));

    const matchedNorm = normName(matched);
    const entry =
      matcher.byName.get(matchedNorm) ||
      matcher.byName.get(matchedNorm.replace(/s$/, ''));

    if (entry) {
      out.push(<OrganBadge key={`${start}-${entry.key}`} entry={entry} onNavigate={onNavigate} />);
    } else {
      out.push(matched);
    }
    last = start + matched.length;
  }

  if (last === 0) return text;
  if (last < text.length) out.push(text.slice(last));
  return out;
}

// Element tags whose text should NOT be linkified (code spans, links, ...)
const SKIP_TAGS = new Set(['code', 'pre', 'a']);

function linkify(node, matcher, onNavigate) {
  if (typeof node === 'string') return splitText(node, matcher, onNavigate);
  if (Array.isArray(node)) return node.map((c) => linkify(c, matcher, onNavigate));
  if (React.isValidElement(node)) {
    const t = node.type;
    // Never re-process our own badges (prevents nested badges)
    if (t === OrganBadge || t === 'button') return node;
    const name = typeof t === 'string' ? t : t?.displayName || t?.name || '';
    if (SKIP_TAGS.has(name)) return node;
    if (node.props?.children !== undefined) {
      return React.cloneElement(node, {}, linkify(node.props.children, matcher, onNavigate));
    }
  }
  return node;
}

// Block-level tags whose text content should get organ badges. Inline tags
// (strong/em/a/code) are covered by their enclosing block, so no double
// processing can occur.
const LINKIFIED_BLOCKS = ['p', 'li', 'td', 'th', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'blockquote'];

/**
 * Returns a `components` map for <ReactMarkdown> that replaces grounded organ
 * mentions with clickable badges inside block-level elements. Returns an empty
 * map when no landmarks are segmented (nothing is grounded -> nothing badges).
 */
export function buildMarkdownComponents(matcher, onNavigate) {
  if (!matcher) return {};
  const components = {};
  for (const tag of LINKIFIED_BLOCKS) {
    const Tag = tag;
    // `node` is react-markdown's internal hast reference — must not reach the DOM
    components[tag] = ({ node, children, ...rest }) => (
      <Tag {...rest}>{linkify(children, matcher, onNavigate)}</Tag>
    );
  }
  return components;
}
