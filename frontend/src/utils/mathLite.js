// ---------------------------------------------------------------------------
// mathLite — lightweight LaTeX-ish cleanup for AI chat output.
// The LLM sometimes emits inline math like "$< 0.3$" or "$3.2 \times 4 mm$".
// Without a math renderer this shows raw $ delimiters and LaTeX commands.
// This converts the math into clean Unicode text rendered in *italic*.
// ---------------------------------------------------------------------------

const SYMBOLS = {
  times: '×', pm: '±', mp: '∓', leq: '≤', geq: '≥', neq: '≠', approx: '≈',
  equiv: '≡', cdot: '·', div: '÷', ll: '≪', gg: '≫', propto: '∝', infty: '∞',
  rightarrow: '→', leftarrow: '←', to: '→', mapsto: '↦',
  mu: 'µ', degree: '°', circ: '°', percent: '%',
  alpha: 'α', beta: 'β', gamma: 'γ', delta: 'δ', epsilon: 'ε', lambda: 'λ',
  pi: 'π', rho: 'ρ', sigma: 'σ', tau: 'τ', omega: 'ω',
  Delta: 'Δ', Gamma: 'Γ', Lambda: 'Λ', Pi: 'Π', Sigma: 'Σ', Omega: 'Ω',
  ldots: '…', dots: '…', text: '', mathrm: '', mathbf: '', textbf: '', textit: '',
};

const SUP = {
  '0': '⁰', '1': '¹', '2': '²', '3': '³', '4': '⁴',
  '5': '⁵', '6': '⁶', '7': '⁷', '8': '⁸', '9': '⁹',
  '+': '⁺', '-': '⁻', '=': '⁼', '(': '⁽', ')': '⁾',
  n: 'ⁿ', i: 'ⁱ', j: 'ʲ', k: 'ᵏ', m: 'ᵐ', o: 'ᵒ', p: 'ᵖ',
  r: 'ʳ', t: 'ᵗ', u: 'ᵘ', v: 'ᵛ', x: 'ˣ', y: 'ʸ',
};

const SUB = {
  '0': '₀', '1': '₁', '2': '₂', '3': '₃', '4': '₄',
  '5': '₅', '6': '₆', '7': '₇', '8': '₈', '9': '₉',
  '+': '₊', '-': '₋', '=': '₌', '(': '₍', ')': '₎',
  a: 'ₐ', e: 'ₑ', h: 'ₕ', i: 'ᵢ', j: 'ⱼ', k: 'ₖ', l: 'ₗ',
  m: 'ₘ', n: 'ₙ', o: 'ₒ', p: 'ₚ', r: 'ᵣ', s: 'ₛ', t: 'ₜ',
  u: 'ᵤ', v: 'ᵥ', x: 'ₓ',
};

const toSup = (s) => [...s].map((c) => SUP[c] ?? c).join('');
const toSub = (s) => [...s].map((c) => SUB[c] ?? c).join('');

function mathToUnicode(src) {
  let s = src;
  // Drop sizing/formatting wrappers
  s = s.replace(/\\(?:left|right|big|Big|bigg|Bigg|displaystyle|limits)\b\s*/g, '');
  // Brace-grouped punctuation: {,} -> ,  (e.g. $1{,}024$)
  s = s.replace(/\{([,.;:!])\}/g, '$1');
  // \command{...} -> keep the argument (e.g. \text{cm})
  s = s.replace(/\\[A-Za-z]+\s*\{([^}]*)\}/g, (m, body) => body);
  // Named symbols (word boundary so \pi doesn't eat \times' letters incorrectly)
  s = s.replace(/\\([A-Za-z]+)/g, (m, name) => (name in SYMBOLS ? SYMBOLS[name] : ' '));
  // Superscripts / subscripts: ^{..} _{..} ^x _x
  s = s.replace(/([_^])\{([^}]*)\}/g, (m, kind, val) => (kind === '^' ? toSup(val) : toSub(val)));
  s = s.replace(/([_^])([A-Za-z0-9+-])/g, (m, kind, ch) => (kind === '^' ? toSup(ch) : toSub(ch)));
  // Escaped specials: \% \& \_ \# \$ etc.
  s = s.replace(/\\([%&#_$])/g, '$1');
  // Thin/medium/thick spaces and any leftover backslash commands
  s = s.replace(/\\[,;:! ]+/g, ' ');
  s = s.replace(/\\[A-Za-z]+/g, '');
  return s.replace(/\s+/g, ' ').trim();
}

// Prevent math content from breaking markdown (bold/italic/links/code)
const escapeMarkdown = (s) => s.replace(/([\\`*_[\]])/g, '\\$1');

/**
 * Converts $...$ inline math and $$...$$ display math in a markdown string
 * into italic Unicode text. Returns the string unchanged when no math is
 * present. Code fences are left untouched.
 */
export default function renderMathish(md) {
  if (typeof md !== 'string' || md.indexOf('$') === -1) return md;

  // Only transform text OUTSIDE fenced code blocks AND inline `code` spans
  return md.split(/(```[\s\S]*?(?:```|$))/g).map((chunk, i) => {
    if (i % 2 === 1) return chunk; // fenced code block — leave as is
    return chunk.split(/(`[^`\n]*`)/g).map((part, j) => {
      if (j % 2 === 1) return part; // inline code span — leave as is

      return part
        // Display math: $$...$$ -> own-line italic
        .replace(/\$\$([\s\S]+?)\$\$/g, (m, body) => `\n\n*${escapeMarkdown(mathToUnicode(body))}*\n\n`)
        // Inline math: $...$ (must start and end with a non-space char,
        // so stray currency like "$5 ... $" is not eaten)
        .replace(/\$(?=\S)([^$\n]*?\S)\$/g, (m, body) => `*${escapeMarkdown(mathToUnicode(body))}*`);
    }).join('');
  }).join('');
}
