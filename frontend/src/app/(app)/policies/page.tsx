"use client";

import { Suspense, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import { FileCheck2, Search } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { RichText } from "@/components/rich-text";
import { ErrorState, LoadingState } from "@/components/states";
import { Card, CardContent } from "@/components/ui/card";
import { anchorId } from "@/lib/policy-ref";
import type { PolicyDocument, PolicyLibrary } from "@/lib/types";
import { useApi } from "@/lib/use-api";
import { cn } from "@/lib/utils";

const TYPE_LABEL: Record<string, string> = {
  policy: "Policies",
  procedure: "Procedures",
  call_script: "Call scripts",
  hardship_programme_terms: "Programme terms",
  regulatory_summary: "Regulatory summaries",
  faq: "FAQ",
  data_contract: "Data contracts",
  incident_report: "Incident reports",
  release_note: "Release notes",
};

const SYNTHETIC = /^>\s*(.*)$/m;

/** The release files open with a notice line and a "# Title" line; show them as metadata, not body. */
function splitPreamble(text: string) {
  const notice = SYNTHETIC.exec(text)?.[1] ?? null;
  const body = text
    .replace(SYNTHETIC, "")
    .replace(/^#\s+.*$/m, "")
    .trim();
  return { notice, body };
}

interface Target {
  doc: PolicyDocument;
  sectionId: string | null;
  note: string | null;
}

/** Resolve ?doc=&v=&s= to the document and section to show, with a note when it isn't an exact match. */
function resolveTarget(docs: PolicyDocument[], doc: string | null, version: string | null, section: string | null): Target | null {
  if (!doc) return null;
  const family = docs.filter((d) => d.doc_id === doc || d.doc_id.startsWith(`${doc}-V`));
  const exact = family.find((d) => !version || d.version === version);
  const found = exact ?? family.find((d) => d.current) ?? family[0];
  if (!found) return null;
  let note: string | null = null;
  if (version && found.version !== version) note = `You followed a link to version ${version}, which isn't in this release. Showing version ${found.version}.`;
  const hasSection = section ? found.sections.some((s) => s.id === section) : false;
  if (section && !hasSection) note = `${section} isn't a section of ${found.doc_id} v${found.version}. Showing the whole document.`;
  return { doc: found, sectionId: hasSection ? section : null, note };
}

function StatusPill({ doc }: { doc: PolicyDocument }) {
  return doc.current ? (
    <span className="bg-accent text-accent-foreground rounded-full px-2.5 py-0.5 text-xs font-medium">Current</span>
  ) : (
    <a
      href={doc.superseded_by ? `#${anchorId(doc.superseded_by)}` : undefined}
      className="bg-amber-soft text-amber-foreground rounded-full px-2.5 py-0.5 text-xs font-medium underline-offset-2 hover:underline"
    >
      Superseded{doc.superseded_by ? ` by ${doc.superseded_by}` : ""}
    </a>
  );
}

function DocumentCard({ doc, target }: { doc: PolicyDocument; target: Target | null }) {
  const { notice, body } = splitPreamble(doc.preamble);
  const isTarget = target?.doc.doc_id === doc.doc_id;
  return (
    <Card id={anchorId(doc.doc_id)} className="scroll-mt-28 gap-0">
      <CardContent className="space-y-5">
        <header className="space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-[1.375rem] leading-snug font-medium">{doc.title}</h2>
            <StatusPill doc={doc} />
          </div>
          <p className="text-muted-foreground text-sm">
            <span className="text-foreground font-mono">{doc.doc_id}</span> version {doc.version}
            {doc.language !== "EN" && <> in {doc.language === "FR" ? "French" : doc.language}</>}
            {doc.effective_date && <>, effective {doc.effective_date}</>}
            {doc.owner && <>, owned by {doc.owner}</>}
          </p>
          <p className="text-muted-foreground flex flex-wrap items-center gap-x-1.5 text-sm">
            <FileCheck2 className="text-primary size-4" aria-hidden />
            Official release file <span className="font-mono text-xs">{doc.file_path}</span>
            <span className="font-mono text-xs" title={`SHA-256 ${doc.sha256}`}>
              (SHA-256 {doc.sha256.slice(0, 12)}…)
            </span>
          </p>
          {notice && <p className="text-muted-foreground text-sm italic">{notice}</p>}
        </header>

        {isTarget && target.note && (
          <p role="status" className="bg-amber-soft text-amber-foreground rounded-xl px-4 py-2.5 text-sm">
            {target.note}
          </p>
        )}

        {body && <RichText markdown text={body} className="text-[0.9375rem] leading-relaxed" />}

        {doc.sections.length > 0 && (
          <div className="space-y-2">
            {doc.sections.map((s) => {
              const active = isTarget && target.sectionId === s.id;
              return (
                <section
                  key={s.id}
                  id={anchorId(doc.doc_id, s.id)}
                  aria-current={active ? "location" : undefined}
                  className={cn(
                    "scroll-mt-28 rounded-xl border-l-4 px-4 py-3",
                    active ? "border-primary bg-accent/60 animate-plan-flash" : "border-transparent",
                  )}
                >
                  <h3 className="font-medium">{s.heading}</h3>
                  {s.text && <RichText markdown text={s.text} className="mt-1.5 text-[0.9375rem] leading-relaxed" />}
                </section>
              );
            })}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function Library() {
  const params = useSearchParams();
  const library = useApi<PolicyLibrary>("/documents");
  const [filter, setFilter] = useState("");
  const docs = useMemo(() => library.data?.documents ?? [], [library.data]);

  const target = useMemo(
    () => resolveTarget(docs, params.get("doc"), params.get("v"), params.get("s")),
    [docs, params],
  );

  // Land on the cited section (or document) once the library has rendered.
  useEffect(() => {
    if (!target) return;
    const id = anchorId(target.doc.doc_id, target.sectionId);
    const frame = window.requestAnimationFrame(() => document.getElementById(id)?.scrollIntoView({ block: "start" }));
    return () => window.cancelAnimationFrame(frame);
  }, [target]);

  const query = filter.trim().toLowerCase();
  const matches = (d: PolicyDocument) =>
    !query ||
    [d.title, d.doc_id, d.preamble, ...d.sections.map((s) => `${s.heading} ${s.text}`)].some((t) => t.toLowerCase().includes(query));
  const shown = docs.filter((d) => matches(d) || d.doc_id === target?.doc.doc_id);

  const groups = useMemo(() => {
    const out: { label: string; items: PolicyDocument[] }[] = [];
    for (const d of shown) {
      const label = d.current ? (TYPE_LABEL[d.doc_type] ?? "Other documents") : "Superseded versions";
      const group = out.find((g) => g.label === label) ?? out[out.push({ label, items: [] }) - 1];
      group.items.push(d);
    }
    return out;
  }, [shown]);

  if (library.loading) return <LoadingState label="Loading the policy library" rows={6} />;
  if (library.error) return <ErrorState message={library.error} onRetry={library.reload} />;

  const release = library.data?.release;
  const index = (
    <nav aria-label="Documents" data-lenis-prevent className="space-y-5 lg:max-h-[calc(100dvh-12rem)] lg:overflow-y-auto lg:pr-2">
      {groups.map((g) => (
        <div key={g.label}>
          <p className="text-muted-foreground mb-1.5 text-sm font-medium">{g.label}</p>
          <ul className="space-y-0.5">
            {g.items.map((d) => {
              const active = target?.doc.doc_id === d.doc_id;
              return (
                <li key={d.doc_id}>
                  <a
                    href={`#${anchorId(d.doc_id)}`}
                    aria-current={active ? "true" : undefined}
                    className={cn(
                      "block rounded-lg px-3 py-2 text-sm leading-snug transition-colors outline-none focus-visible:ring-[3px] focus-visible:ring-ring/35",
                      active ? "bg-accent text-accent-foreground font-medium" : "hover:bg-card",
                    )}
                  >
                    {d.title}
                    <span className="text-muted-foreground block font-mono text-xs">
                      {d.doc_id} v{d.version}
                    </span>
                  </a>
                </li>
              );
            })}
          </ul>
        </div>
      ))}
    </nav>
  );

  return (
    <div className="space-y-8">
      <p className="text-muted-foreground flex items-start gap-2 text-sm">
        <FileCheck2 className="text-primary mt-0.5 size-4 shrink-0" aria-hidden />
        <span>
          {docs.length} documents, word for word from the Maple Bank release files
          {release?.revision ? ` (release ${release.revision.slice(0, 7)}` : ""}
          {release?.revision ? (release.verified_against_publisher ? ", checksum verified against the publisher)." : ").") : "."}
        </span>
      </p>

      <div className="grid gap-8 lg:grid-cols-[17rem_1fr] lg:gap-10">
        <aside className="space-y-4 lg:sticky lg:top-24 lg:self-start">
          <label className="relative block">
            <span className="sr-only">Search policies</span>
            <Search className="text-muted-foreground pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2" aria-hidden />
            <input
              type="search"
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              placeholder="Search policies"
              className="bg-card border-input focus-visible:border-primary focus-visible:ring-primary/25 h-10 w-full rounded-xl border pr-3 pl-9 text-sm outline-none focus-visible:ring-4"
            />
          </label>
          <details className="lg:hidden">
            <summary className="cursor-pointer text-sm font-medium">All documents ({shown.length})</summary>
            <div className="mt-3">{index}</div>
          </details>
          <div className="hidden lg:block">{index}</div>
        </aside>

        <div className="min-w-0 space-y-6">
          {shown.length ? (
            shown.map((d) => <DocumentCard key={d.doc_id} doc={d} target={target} />)
          ) : (
            <p className="text-muted-foreground">No document mentions &ldquo;{filter}&rdquo;.</p>
          )}
        </div>
      </div>
    </div>
  );
}

export default function PoliciesPage() {
  return (
    <>
      <PageHeader
        title="Policies and procedures"
        description="The official text behind every rule the app cites. Click a citation such as POL-COLL-001 v3.0 §5.4 anywhere in the app to land on that section here."
      />
      <Suspense fallback={<LoadingState label="Loading the policy library" rows={6} />}>
        <Library />
      </Suspense>
    </>
  );
}
