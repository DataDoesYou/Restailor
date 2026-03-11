// Client-side hashing utilities mirroring backend hash_utils.py
// Normalization: remove BOM/zero-width, unify newlines to \n, collapse whitespace to single spaces, trim.

const ZERO_WIDTH_RE = /[\u200B\u200C\u200D\uFEFF]/g; // BOM & zero-width
const WHITESPACE_RE = /\s+/g; // collapse all whitespace (incl newlines, tabs)
const CONTROL_CHARS_RE = /[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]/g;

export function normalizeText(input: string): string {
  if (input == null) return "";
  let s = input.replace(/\r\n/g, "\n").replace(/\r/g, "\n");
  
  // Strip HTML tags (match backend logic)
  // Remove script/style blocks
  s = s.replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi, " ");
  s = s.replace(/<style\b[^>]*>[\s\S]*?<\/style>/gi, " ");
  // Remove all tags
  s = s.replace(/<[^>]+>/g, " ");
  
  // Unescape entities
  if (typeof window !== 'undefined' && typeof DOMParser !== 'undefined') {
    try {
      const doc = new DOMParser().parseFromString(s, "text/html");
      s = doc.documentElement.textContent || "";
    } catch (e) {
      // Fallback if DOMParser fails
    }
  } else {
    // Basic fallback for non-browser environments
    s = s.replace(/&amp;/g, "&")
         .replace(/&lt;/g, "<")
         .replace(/&gt;/g, ">")
         .replace(/&quot;/g, '"')
         .replace(/&#39;/g, "'")
         .replace(/&nbsp;/g, " ");
  }

  s = s.replace(ZERO_WIDTH_RE, "");
  s = s.replace(CONTROL_CHARS_RE, "");
  s = s.replace(WHITESPACE_RE, " ");
  return s.trim();
}

export async function stableHash(input: string): Promise<string> {
  const enc = new TextEncoder();
  const data = enc.encode(input);
  const digest = await crypto.subtle.digest("SHA-256", data);
  return Array.from(new Uint8Array(digest))
    .map(b => b.toString(16).padStart(2, "0"))
    .join("");
}

export async function makeAppliedKey(userId: string, jdText: string, baseText: string): Promise<{ jdHash: string; baseHash: string; appliedKey: string; }> {
  const normJd = normalizeText(jdText);
  const normBase = normalizeText(baseText);
  const [jdHash, baseHash] = await Promise.all([stableHash(normJd), stableHash(normBase)]);
  return { jdHash, baseHash, appliedKey: `${userId}:${jdHash}:${baseHash}` };
}

// New: compute just the JD hash (single-snapshot-per-JD logic)
export async function makeJdHash(jdText: string): Promise<string> {
  return stableHash(normalizeText(jdText));
}
