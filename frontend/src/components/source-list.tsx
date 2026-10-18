import { PolicyLink } from "@/components/policy-link";
import { parseCitation } from "@/lib/policy-ref";
import { displayValue } from "@/lib/utils";

/** Lists source references (policy files, tables, transcripts) as returned. */
export function SourceList({ sources, empty = "No sources listed." }: { sources: unknown[] | null | undefined; empty?: string }) {
  if (!sources?.length) return <p className="text-muted-foreground text-sm">{empty}</p>;
  return (
    <ul className="space-y-1.5 text-sm">
      {sources.map((source, i) => {
        const text = displayValue(source);
        // Policy citations open the official text; other sources (tables, files) stay as text.
        return typeof source === "string" && parseCitation(text) ? (
          <li key={i}>
            <PolicyLink text={text} className="w-full rounded-md px-3 py-1.5" />
          </li>
        ) : (
          <li key={i} className="bg-muted/60 rounded-md px-3 py-1.5 font-mono text-xs break-words">
            {text}
          </li>
        );
      })}
    </ul>
  );
}
