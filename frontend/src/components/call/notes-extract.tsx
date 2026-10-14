"use client";

import { useState } from "react";
import { Check, CheckCheck, Loader2, Sparkles, Wand2, X } from "lucide-react";
import { ErrorState } from "@/components/states";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { errorMessage } from "@/lib/api";
import type { ExtractProposal, ExtractResponse } from "@/lib/call-types";
import { fieldLabel, valueLabel } from "@/lib/call-outcomes";
import { extractFromNote } from "@/lib/use-call-session";
import { cn } from "@/lib/utils";
import { CallStep } from "./guided-call";

type Item = ExtractProposal & { id: number; state: "pending" | "accepted" };

/** Shows the quote inside its surrounding note text, with the quote marked. */
function QuoteInContext({ note, quote }: { note: string; quote: string }) {
  const at = quote ? note.toLowerCase().indexOf(quote.toLowerCase()) : -1;
  if (at < 0) {
    return (
      <p className="text-sm leading-relaxed">
        <mark className="bg-review-soft text-foreground rounded px-0.5">{quote}</mark>
      </p>
    );
  }
  const before = note.slice(Math.max(0, at - 50), at);
  const after = note.slice(at + quote.length, at + quote.length + 50);
  return (
    <p className="text-muted-foreground text-sm leading-relaxed break-words">
      {at > 50 && "…"}
      {before}
      <mark className="bg-review-soft text-foreground rounded px-0.5 font-medium">{note.slice(at, at + quote.length)}</mark>
      {after}
      {at + quote.length + 50 < note.length && "…"}
    </p>
  );
}

export function NotesExtract({
  customerId,
  onAccept,
}: {
  customerId: string;
  /** applies one proposal to the outcomes; returns a short description of what happened */
  onAccept: (proposal: ExtractProposal) => void;
}) {
  const [note, setNote] = useState("");
  const [extractedFrom, setExtractedFrom] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<Pick<ExtractResponse, "provider" | "message"> | null>(null);
  const [items, setItems] = useState<Item[]>([]);

  async function extract() {
    const text = note.trim();
    if (!text) return;
    setPending(true);
    setError(null);
    try {
      const response = await extractFromNote(customerId, text);
      setResult({ provider: response.provider, message: response.message });
      setExtractedFrom(text);
      setItems(response.proposals.map((p, i) => ({ ...p, id: Date.now() + i, state: "pending" })));
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setPending(false);
    }
  }

  function accept(item: Item) {
    onAccept(item);
    setItems((all) => all.map((x) => (x.id === item.id ? { ...x, state: "accepted" } : x)));
  }

  const open = items.filter((i) => i.state === "pending");

  return (
    <CallStep n={4} title="Call notes" hint="Type what the customer said. Extract turns it into suggested outcomes; you accept each one.">
      <div className="space-y-3">
        <Label htmlFor="call-notes" className="sr-only">
          Call notes
        </Label>
        <Textarea
          id="call-notes"
          value={note}
          onChange={(e) => setNote(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
              e.preventDefault();
              void extract();
            }
          }}
          placeholder="e.g. Lost his job in August. Can pay $200 on Oct 9. Thinks the late fee is wrong."
          className="min-h-28 leading-relaxed"
        />
        <div className="flex flex-wrap items-center gap-3">
          <Button type="button" onClick={extract} disabled={pending || !note.trim()}>
            {pending ? <Loader2 className="animate-spin" aria-hidden /> : <Wand2 aria-hidden />}
            {pending ? "Reading notes…" : "Extract from notes"}
          </Button>
          <span className="text-muted-foreground text-xs">Ctrl + Enter. Nothing changes until you accept a suggestion.</span>
        </div>
      </div>

      <div aria-live="polite" className="mt-4 space-y-3">
        {error && <ErrorState title="Could not read the notes" message={error} onRetry={extract} />}
        {result && !error && (
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="text-sm">
              <span className="font-medium">
                {items.length ? `${items.length} suggestion${items.length === 1 ? "" : "s"}` : "No suggestions"}
              </span>
              <span className="text-muted-foreground"> from {result.provider === "gemini" ? "Gemini" : "local rules"}</span>
              {result.message && <span className="text-muted-foreground block text-xs">{result.message}</span>}
            </p>
            {open.length > 1 && (
              <Button type="button" variant="outline" size="sm" onClick={() => open.forEach(accept)}>
                <CheckCheck aria-hidden /> Accept all {open.length}
              </Button>
            )}
          </div>
        )}
        {items.length > 0 && (
          <ul className="space-y-2">
            {items.map((item) => (
              <li
                key={item.id}
                className={cn(
                  "rounded-lg border p-3 transition-colors",
                  item.state === "accepted" ? "border-success/25 bg-success-soft/50" : "bg-background",
                )}
              >
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <p className="min-w-0 text-sm">
                    <span className="text-muted-foreground">{fieldLabel(item.field)}: </span>
                    <strong>{valueLabel(item.field, item.value)}</strong>
                  </p>
                  <Badge variant={item.source === "gemini" ? "teal" : "outline"}>
                    {item.source === "gemini" ? <Sparkles aria-hidden /> : null}
                    {item.source === "gemini" ? "Gemini" : "Rules"}
                  </Badge>
                </div>
                <div className="mt-1.5">
                  <QuoteInContext note={extractedFrom} quote={item.quote} />
                </div>
                <div className="mt-2.5 flex items-center gap-2">
                  {item.state === "accepted" ? (
                    <span className="text-success flex items-center gap-1 text-sm font-medium">
                      <Check className="size-4" aria-hidden /> Applied
                    </span>
                  ) : (
                    <>
                      <Button type="button" size="sm" onClick={() => accept(item)} aria-label={`Accept: ${fieldLabel(item.field)}, ${valueLabel(item.field, item.value)}`}>
                        <Check aria-hidden /> Accept
                      </Button>
                      <Button
                        type="button"
                        size="sm"
                        variant="ghost"
                        onClick={() => setItems((all) => all.filter((x) => x.id !== item.id))}
                        aria-label={`Dismiss: ${fieldLabel(item.field)}`}
                      >
                        <X aria-hidden /> Dismiss
                      </Button>
                    </>
                  )}
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </CallStep>
  );
}
