"use client";

import Link from "next/link";
import { useState } from "react";
import { ArrowRight, CalendarClock, CircleAlert, ClipboardCheck, Loader2, RotateCcw, Send } from "lucide-react";
import { ErrorState } from "@/components/states";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { errorMessage } from "@/lib/api";
import type { Outcomes, SubmitResponse, WrapUp } from "@/lib/call-types";
import { submitCall } from "@/lib/use-call-session";

export function WrapUpPanel({
  customerId,
  wrapUp,
  outcomes,
  stale,
  submitted,
  onSubmitted,
}: {
  customerId: string;
  wrapUp: WrapUp;
  outcomes: Outcomes;
  /** true while a recompute is pending, so the shown result may lag behind the latest change */
  stale: boolean;
  submitted: SubmitResponse | null;
  onSubmitted: (result: SubmitResponse) => void;
}) {
  // The note follows the generated text until the agent edits it; after that the agent's text wins.
  const [edited, setEdited] = useState<{ text: string; base: string } | null>(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const note = edited?.text ?? wrapUp.note;
  const newerGenerated = edited !== null && edited.base !== wrapUp.note;

  async function submit() {
    setPending(true);
    setError(null);
    try {
      onSubmitted(await submitCall(customerId, outcomes, note));
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setPending(false);
    }
  }

  if (submitted) {
    return (
      <Alert variant="info" className="py-4">
        <ClipboardCheck aria-hidden />
        <AlertTitle className="text-base">Sent for supervisor review</AlertTitle>
        <AlertDescription>
          <p>
            Call record <span className="font-mono">{submitted.brief_id}</span> is {submitted.status}. Nothing has been sent to the customer.
          </p>
          <Button asChild size="sm" className="mt-2">
            <Link href="/reviews">
              Open supervisor review <ArrowRight aria-hidden />
            </Link>
          </Button>
        </AlertDescription>
      </Alert>
    );
  }

  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)]">
      <div className="space-y-2">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <Label htmlFor="wrap-note">Call note for the record</Label>
          {edited && (
            <Button type="button" variant="ghost" size="sm" onClick={() => setEdited(null)}>
              <RotateCcw aria-hidden /> {newerGenerated ? "Use the updated generated note" : "Reset to generated note"}
            </Button>
          )}
        </div>
        <Textarea
          id="wrap-note"
          value={note}
          onChange={(e) => setEdited({ text: e.target.value, base: edited?.base ?? wrapUp.note })}
          className="min-h-40 leading-relaxed"
        />
        <p className="text-muted-foreground text-xs">
          {edited ? "Edited by you. The generated note keeps updating underneath." : "Generated from the outcomes you recorded. Edit it if anything is missing."}
        </p>
      </div>

      <div className="space-y-4">
        <div>
          <h4 className="text-muted-foreground mb-1.5 text-xs font-medium">Outcome codes</h4>
          {wrapUp.outcome_codes.length ? (
            <div className="flex flex-wrap gap-1.5">
              {wrapUp.outcome_codes.map((c) => (
                <Badge key={c} variant="teal" className="font-mono">
                  {c}
                </Badge>
              ))}
            </div>
          ) : (
            <p className="text-muted-foreground text-sm">None yet.</p>
          )}
        </div>
        {wrapUp.follow_ups.length > 0 && (
          <div>
            <h4 className="text-muted-foreground mb-1.5 text-xs font-medium">Follow-ups</h4>
            <ul className="space-y-1.5">
              {wrapUp.follow_ups.map((f, i) => (
                <li key={`${f.type}-${i}`} className="flex gap-2 text-sm">
                  <CalendarClock className="text-primary mt-0.5 size-4 shrink-0" aria-hidden />
                  <span>
                    <strong className="capitalize">{f.type.replace(/_/g, " ")}</strong>, {f.when}.{" "}
                    <span className="text-muted-foreground">{f.reason}</span>
                  </span>
                </li>
              ))}
            </ul>
          </div>
        )}
        {wrapUp.blocking.length > 0 && (
          <div className="border-destructive/25 bg-destructive/5 rounded-lg border p-3">
            <h4 className="text-destructive mb-1.5 flex items-center gap-1.5 text-sm font-semibold">
              <CircleAlert className="size-4" aria-hidden /> Resolve before submitting
            </h4>
            <ul className="list-disc space-y-1 pl-5 text-sm">
              {wrapUp.blocking.map((b) => (
                <li key={b}>{b}</li>
              ))}
            </ul>
          </div>
        )}
        {error && <ErrorState title="Not submitted" message={error} />}
        <Button type="button" size="lg" className="w-full" onClick={submit} disabled={!wrapUp.ready_to_submit || pending || stale || !note.trim()}>
          {pending ? <Loader2 className="animate-spin" aria-hidden /> : <Send aria-hidden />}
          {pending ? "Submitting…" : "Submit for supervisor review"}
        </Button>
        <p className="text-muted-foreground text-xs">A supervisor reviews the call record. Nothing is sent to the customer.</p>
      </div>
    </div>
  );
}
