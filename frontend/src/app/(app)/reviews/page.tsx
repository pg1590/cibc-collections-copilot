"use client";

import Link from "next/link";
import { useId, useState } from "react";
import { Check, ChevronDown, History, Loader2, PencilLine, RotateCw, X } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { RecordTable } from "@/components/record-table";
import { RoleGate } from "@/components/role-gate";
import { SourceList } from "@/components/source-list";
import { EmptyState, ErrorState, LoadingState } from "@/components/states";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { api, errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useApi } from "@/lib/use-api";
import type { ApiRecord, AuditEvent, Decision, ReviewItem } from "@/lib/types";
import { cn, formatDateTime } from "@/lib/utils";

const DECISIONS: { value: Decision; label: string; icon: typeof Check }[] = [
  { value: "approve", label: "Approve", icon: Check },
  { value: "edit", label: "Edit and approve", icon: PencilLine },
  { value: "reject", label: "Reject", icon: X },
];

function isPending(item: ReviewItem) {
  return item.status === "pending" && !item.decision;
}

function StatusBadge({ item }: { item: ReviewItem }) {
  if (isPending(item)) return <Badge variant="review">Pending review</Badge>;
  if (item.decision === "reject") return <Badge variant="destructive">Rejected</Badge>;
  if (item.decision === "edit") return <Badge variant="success">Edited</Badge>;
  if (item.decision === "approve") return <Badge variant="success">Approved</Badge>;
  return <Badge variant="outline">{item.status}</Badge>;
}

function DecisionForm({ item, onDone }: { item: ReviewItem; onDone: (updated: ReviewItem) => void }) {
  const uid = useId();
  const [decision, setDecision] = useState<Decision | null>(null);
  const [reason, setReason] = useState("");
  const [draft, setDraft] = useState(item.draft ?? "");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const draftChanged = draft.trim() !== (item.draft ?? "").trim();
  const invalid = !decision || !reason.trim() || (decision === "edit" && (!draft.trim() || !draftChanged));

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (invalid || !decision) return;
    setPending(true);
    setError(null);
    try {
      const body: { decision: Decision; reason: string; draft?: string } = { decision, reason: reason.trim() };
      if (decision === "edit") body.draft = draft;
      const updated = await api<ReviewItem>(`/reviews/${encodeURIComponent(item.brief_id)}`, {
        method: "POST",
        body: JSON.stringify(body),
      });
      onDone(updated);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setPending(false);
    }
  }

  return (
    <form onSubmit={submit} className="space-y-4 border-t pt-5">
      <fieldset>
        <legend className="mb-2 text-sm font-medium">Decision</legend>
        <div className="flex flex-wrap gap-2">
          {DECISIONS.map(({ value, label, icon: Icon }) => (
            <label
              key={value}
              className={cn(
                "flex cursor-pointer items-center gap-2 rounded-md border px-3 py-2 text-sm transition-colors has-[:focus-visible]:ring-[3px] has-[:focus-visible]:ring-ring/30",
                decision === value
                  ? value === "reject"
                    ? "border-destructive bg-destructive/5 text-destructive"
                    : "border-primary bg-accent/60 text-accent-foreground"
                  : "bg-card hover:bg-muted",
              )}
            >
              <input
                type="radio"
                name={`${uid}-decision`}
                value={value}
                checked={decision === value}
                onChange={() => setDecision(value)}
                className="sr-only"
              />
              <Icon className="size-4" aria-hidden />
              {label}
            </label>
          ))}
        </div>
      </fieldset>

      {decision === "edit" && (
        <div className="space-y-2">
          <Label htmlFor={`${uid}-draft`}>Edited draft</Label>
          <Textarea
            id={`${uid}-draft`}
            required
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            className="min-h-32 leading-relaxed"
            aria-describedby={`${uid}-draft-help`}
          />
          <p id={`${uid}-draft-help`} className="text-muted-foreground text-xs">
            {draftChanged ? "Your edited text will replace the model draft." : "Change the draft to submit an edit."}
          </p>
        </div>
      )}

      <div className="space-y-2">
        <Label htmlFor={`${uid}-reason`}>
          Reason <span className="text-muted-foreground font-normal">(required, kept in the audit log)</span>
        </Label>
        <Textarea
          id={`${uid}-reason`}
          required
          rows={2}
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          placeholder="Why are you making this decision?"
        />
      </div>

      {error && (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      <div className="flex flex-wrap items-center gap-3">
        <Button type="submit" disabled={pending || invalid} variant={decision === "reject" ? "destructive" : "default"}>
          {pending && <Loader2 className="animate-spin" aria-hidden />}
          {pending ? "Recording…" : "Record decision"}
        </Button>
        <p className="text-muted-foreground text-xs">Recording a decision does not contact the customer.</p>
      </div>
    </form>
  );
}

function ReviewCard({ item, canDecide, onUpdated }: { item: ReviewItem; canDecide: boolean; onUpdated: (u: ReviewItem) => void }) {
  return (
    <Card className={cn(isPending(item) && "border-l-review border-l-4")}>
      <CardHeader>
        <CardDescription className="flex flex-wrap gap-x-3">
          <span>
            Customer{" "}
            <Link href={`/customers/${encodeURIComponent(item.customer_id)}`} className="font-mono underline underline-offset-4">
              {item.customer_id}
            </Link>
          </span>
          <span>Created {formatDateTime(item.created_at)}</span>
          <span className="font-mono text-xs">{item.brief_id}</span>
        </CardDescription>
        <CardTitle className="leading-snug font-medium">{item.summary}</CardTitle>
        <CardAction>
          <StatusBadge item={item} />
        </CardAction>
      </CardHeader>
      <CardContent className="space-y-4">
        {item.summary_evidence && (
          <section aria-label="Supporting evidence" className="bg-muted/40 rounded-md border p-3">
            <h3 className="text-muted-foreground mb-2 text-sm font-medium">Supporting evidence</h3>
            <p className="text-sm leading-relaxed whitespace-pre-line">{item.summary_evidence}</p>
          </section>
        )}
        {item.generation && (
          <p className="text-muted-foreground text-sm">
            {item.generation.status === "generated" && item.generation.provider.toLowerCase() === "gemini"
              ? "Gemini-assisted draft based on the recorded facts and policy evidence."
              : item.generation.status === "fallback"
                ? "AI assistance was unavailable. This draft uses the recorded facts and local rules."
                : "Draft prepared from the recorded facts and local rules."}
          </p>
        )}
        {item.hardship_status && (
          <div className="rounded-md border p-3 text-sm">
            <h3 className="mb-1 font-medium">Hardship evidence</h3>
            <p>
              {item.hardship_status === "recorded"
                ? "Financial hardship is recorded in the case history. Confirm the customer’s current circumstances."
                : item.hardship_status === "possible"
                  ? "Possible financial hardship needs confirmation by a reviewer."
                  : "Financial hardship is not established by the available evidence. Hardship may still be present."}
            </p>
            {!!item.recorded_hardship_cases?.length && (
              <div className="mt-2">
                <p className="text-muted-foreground mb-1 text-xs">Recorded case references</p>
                <SourceList sources={item.recorded_hardship_cases} />
              </div>
            )}
          </div>
        )}
        <div>
          <h3 className="text-muted-foreground text-xs font-medium tracking-wide uppercase">Recommendation</h3>
          <p className="mt-1 leading-relaxed whitespace-pre-line">{item.recommendation}</p>
          {item.recommendation_reason && (
            <div className="mt-3">
              <h3 className="text-muted-foreground text-xs font-medium tracking-wide uppercase">Why this recommendation</h3>
              <p className="mt-1 text-sm leading-relaxed whitespace-pre-line">{item.recommendation_reason}</p>
            </div>
          )}
        </div>
        {!!item.policy_sources?.length && (
          <div>
            <h3 className="text-muted-foreground mb-2 text-xs font-medium tracking-wide uppercase">Policy sources</h3>
            <SourceList sources={item.policy_sources} />
          </div>
        )}
        {!!item.signals?.length && (
          <Collapsible>
            <CollapsibleTrigger asChild>
              <Button variant="outline" size="sm" className="group">
                Signals and evidence <ChevronDown className="transition-transform group-data-[state=open]:rotate-180" aria-hidden />
              </Button>
            </CollapsibleTrigger>
            <CollapsibleContent className="mt-3">
              <RecordTable records={item.signals.map((signal) => ({ ...signal }))} caption="Brief signals and evidence" />
            </CollapsibleContent>
          </Collapsible>
        )}
        <div>
          <h3 className="text-muted-foreground text-xs font-medium tracking-wide uppercase">
            {item.decision === "edit" ? "Edited draft" : "Draft"}
          </h3>
          <p className="bg-muted/50 mt-1 rounded-md border p-3 text-sm leading-relaxed whitespace-pre-line">{item.draft}</p>
        </div>
        {!isPending(item) && (item.reason || item.reviewer) && (
          <div className="text-sm">
            <span className="text-muted-foreground">Reviewed by </span>
            <span className="font-medium">{item.reviewer ?? "—"}</span>
            {item.reason && (
              <>
                <span className="text-muted-foreground"> · Reason: </span>
                {item.reason}
              </>
            )}
          </div>
        )}
        {isPending(item) && canDecide && <DecisionForm item={item} onDone={onUpdated} />}
      </CardContent>
    </Card>
  );
}

function AuditLog() {
  const audit = useApi<{ items: AuditEvent[] }>("/audit");
  return (
    <Collapsible className="mt-10">
      <CollapsibleTrigger asChild>
        <Button variant="outline" className="group">
          <History aria-hidden /> Audit log
          <ChevronDown className="transition-transform group-data-[state=open]:rotate-180" aria-hidden />
        </Button>
      </CollapsibleTrigger>
      <CollapsibleContent className="mt-4 space-y-3">
        <div className="flex justify-end">
          <Button variant="ghost" size="sm" onClick={audit.reload}>
            <RotateCw aria-hidden /> Refresh
          </Button>
        </div>
        {audit.loading ? (
          <LoadingState label="Loading audit log" />
        ) : audit.error ? (
          <ErrorState message={audit.error} onRetry={audit.reload} />
        ) : (
          <RecordTable
            records={(audit.data?.items ?? []).map((e) => ({ ...e, at: formatDateTime(e.at) }) as unknown as ApiRecord)}
            caption="Audit events"
            emptyTitle="No audit events yet"
          />
        )}
      </CollapsibleContent>
    </Collapsible>
  );
}

export default function ReviewsPage() {
  const { session } = useAuth();
  const isSupervisor = session?.user.role === "supervisor";
  const reviews = useApi<{ items: ReviewItem[] }>("/reviews");
  const [overrides, setOverrides] = useState<Record<string, ReviewItem>>({});

  const items = (reviews.data?.items ?? []).map((item) => overrides[item.brief_id] ?? item);
  const pending = items.filter(isPending);
  const decided = items.filter((i) => !isPending(i));
  const onUpdated = (updated: ReviewItem) => setOverrides((o) => ({ ...o, [updated.brief_id]: updated }));

  const list = (rows: ReviewItem[], empty: string) =>
    rows.length ? (
      <div className="space-y-5">
        {rows.map((item) => (
          <ReviewCard key={item.brief_id} item={item} canDecide={isSupervisor} onUpdated={onUpdated} />
        ))}
      </div>
    ) : (
      <EmptyState title={empty} />
    );

  return (
    <>
      <PageHeader
        title="Supervisor review"
        description={
          isSupervisor
            ? "Approve, edit or reject each draft brief. Every decision needs a reason and is written to the audit log."
            : "Track the review status of draft briefs. Only supervisors can record decisions."
        }
        actions={
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              setOverrides({});
              reviews.reload();
            }}
          >
            <RotateCw aria-hidden /> Refresh
          </Button>
        }
      />
      <RoleGate section="reviews">
        {reviews.loading ? (
          <LoadingState label="Loading review queue" />
        ) : reviews.error ? (
          <ErrorState message={reviews.error} onRetry={reviews.reload} />
        ) : (
          <Tabs defaultValue="pending">
            <TabsList aria-label="Review queue filter">
              <TabsTrigger value="pending">
                Pending
                <Badge variant={pending.length ? "review" : "secondary"} className="ml-1">
                  {pending.length}
                </Badge>
              </TabsTrigger>
              <TabsTrigger value="decided">
                Decided
                <Badge variant="secondary" className="ml-1">
                  {decided.length}
                </Badge>
              </TabsTrigger>
            </TabsList>
            <TabsContent value="pending">{list(pending, "Nothing waiting for review")}</TabsContent>
            <TabsContent value="decided">{list(decided, "No decisions recorded yet")}</TabsContent>
          </Tabs>
        )}
        {isSupervisor && <AuditLog />}
      </RoleGate>
    </>
  );
}
