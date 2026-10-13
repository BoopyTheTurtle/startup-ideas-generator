// Stored bodies may hold HTML. This turns them into plain text for display; callers
// render the result as a React text node, never as HTML. Mirrors pipeline/text.py.

const BLOCK = new Set([
  "p", "div", "br", "li", "ul", "ol", "tr", "h1", "h2", "h3", "h4", "h5", "h6",
  "blockquote", "pre", "table", "section", "article", "hr",
]);

const NAMED: Record<string, string> = {
  amp: "&", lt: "<", gt: ">", quot: '"', apos: "'", nbsp: " ", hellip: "…",
  mdash: "—", ndash: "–", lsquo: "‘", rsquo: "’", ldquo: "“", rdquo: "”",
  laquo: "«", raquo: "»", euro: "€", pound: "£", copy: "©", reg: "®", trade: "™",
  eacute: "é", egrave: "è", agrave: "à", ccedil: "ç", uuml: "ü", ouml: "ö", auml: "ä",
  szlig: "ß", bull: "•", middot: "·", deg: "°",
};

function decodeEntities(s: string): string {
  return s.replace(/&(#x[0-9a-f]+|#[0-9]+|[a-z]+);/gi, (whole, ent: string) => {
    if (ent[0] === "#") {
      const code = ent[1] === "x" || ent[1] === "X" ? parseInt(ent.slice(2), 16) : parseInt(ent.slice(1), 10);
      return code > 0 && code <= 0x10ffff ? String.fromCodePoint(code) : whole;
    }
    return NAMED[ent.toLowerCase()] ?? whole;
  });
}

export function plainText(body: string): string {
  let text: string;
  if (body.includes("<") && body.includes(">")) {
    text = body
      .replace(/<(script|style)\b[^>]*>[\s\S]*?<\/\1\s*>/gi, "")
      .replace(/<!--[\s\S]*?-->/g, "")
      .replace(/<\/?([a-zA-Z][a-zA-Z0-9]*)\b[^>]*>/g, (_m, tag: string) =>
        BLOCK.has(tag.toLowerCase()) ? "\n" : "",
      );
    text = decodeEntities(text);
  } else {
    text = decodeEntities(body);
  }
  return text
    .replace(/[ \t\r\f\v ]+/g, " ")
    .replace(/ ?\n ?/g, "\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

// Only http(s) links reach an href; anything else (javascript:, data:) is dropped.
export function safeUrl(url: string | null): string | null {
  if (!url) return null;
  try {
    const u = new URL(url);
    return u.protocol === "http:" || u.protocol === "https:" ? u.href : null;
  } catch {
    return null;
  }
}
