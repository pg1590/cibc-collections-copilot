/**
 * Citations look like "POL-COLL-001 v3.0 §5.4", "PRC-COLL-010 v2.1 §3.1", "SCR-MID-STD-EN v2.0"
 * or "FAQ-COLL-001 Q2". Anything else is not treated as a citation.
 */
const CITATION = /^([A-Z]{2,4}(?:-[A-Z0-9]+)+)(?:\s+v([\d.]+))?(?:\s+(§\d+(?:\.\d+)*(?:\s*[-–]\s*[\d.]+)?|Q\d+))?$/;

export interface Citation {
  doc: string;
  version: string | null;
  /** The first section a citation points to, e.g. "§4.5" for "§4.5-4.6". */
  section: string | null;
}

export function parseCitation(text: string): Citation | null {
  const match = CITATION.exec(text.trim());
  if (!match) return null;
  const section = match[3] ? match[3].split(/\s*[-–]\s*/)[0] : null;
  return { doc: match[1], version: match[2] ?? null, section };
}

export function citationHref({ doc, version, section }: Citation): string {
  const query = new URLSearchParams({ doc });
  if (version) query.set("v", version);
  if (section) query.set("s", section);
  return `/policies?${query.toString()}`;
}

/** DOM id for a document or one of its sections, safe for CSS selectors. */
export function anchorId(docId: string, section?: string | null): string {
  const base = `doc-${docId}`;
  return section ? `${base}-s-${section.replace(/[^A-Za-z0-9]+/g, "-").replace(/^-|-$/g, "")}` : base;
}
