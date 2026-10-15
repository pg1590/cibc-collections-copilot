"use client";

import Link from "next/link";
import { Suspense, useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { ArrowRight, Cpu, Hourglass, Loader2, PhoneCall, Sparkles } from "lucide-react";
import { ActionPlanCard } from "@/components/action-plan";
import { PageHeader } from "@/components/page-header";
import { KeyValueList } from "@/components/record-table";
import { RoleGate } from "@/components/role-gate";
import { SourceList } from "@/components/source-list";
import { EmptyState, ErrorState } from "@/components/states";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { api, errorMessage } from "@/lib/api";
import type { BriefWithPlan as Brief } from "@/lib/plan-types";
import { displayValue } from "@/lib/utils";

function BriefView({ brief }: { brief: Brief }) {
  const draftTitle = brief.contact_hold ? "Internal note — do not contact the customer" : "Draft message";
  return (
    <div className="space-y-8">
      <Alert variant="review">
        <Hourglass aria-hidden />
        <AlertTitle>Waiting for supervisor review</AlertTitle>
        <AlertDescription>
          <p>
            This brief is a draft (status: <strong>{brief.status}</strong>). It is not sent to anyone. A supervisor must
            approve, edit or reject it, with a reason.
          </p>
        </AlertDescription>
      </Alert>

      {brief.action_plan && <ActionPlanCard plan={brief.action_plan} />}

      <div className="flex flex-col gap-3 rounded-xl border border-primary/25 bg-accent/40 p-4 sm:flex-row sm:items-center sm:justify-between">
        <p className="text-sm leading-relaxed">
          <strong>Ready to call?</strong> Call mode walks you through this plan and updates it as the customer answers.
        </p>
        <Button asChild className="shrink-0">
          <Link href={`/call/${encodeURIComponent(brief.customer_id)}`}>
            <PhoneCall aria-hidden /> Start call
          </Link>
        </Button>
      </div>

      <Card>
        <CardHeader>
          <CardDescription>
            Brief <span className="font-mono">{brief.brief_id}</span> · customer{" "}
            <Link className="font-mono underline underline-offset-4" href={`/customers/${encodeURIComponent(brief.customer_id)}`}>
              {brief.customer_id}
            </Link>
          </CardDescription>
          <CardTitle className="text-lg">Summary</CardTitle>
        </CardHeader>
        <CardContent className="space-y-6">
          {brief.generation && (
            <p className="text-muted-foreground text-sm">
              {brief.generation.status === "generated" && brief.generation.provider.toLowerCase() === "gemini"
                ? brief.contact_hold
                  ? "Gemini evidence accompanies the internal note; the recorded contact restriction still applies."
                  : "Gemini-assisted draft based on the recorded facts and policy evidence."
                : brief.generation.status === "fallback"
                  ? brief.contact_hold
                    ? "AI evidence assistance was unavailable. The internal note follows the recorded restrictions and local rules."
                    : "AI assistance was unavailable. This draft uses the recorded facts and local rules."
                  : brief.contact_hold
                    ? "Internal note prepared from the recorded restrictions and local rules."
                    : "Draft prepared from the recorded facts and local rules."}
            </p>
          )}
          <p className="leading-relaxed whitespace-pre-line">{brief.summary}</p>
          {brief.summary_evidence && (
            <section aria-label="Supporting evidence" className="bg-muted/40 rounded-lg border p-4">
              <h3 className="text-muted-foreground mb-2 text-sm font-medium">Supporting evidence</h3>
              <p className="text-sm leading-relaxed whitespace-pre-line">{brief.summary_evidence}</p>
            </section>
          )}
          {brief.hardship_status && (
            <div className="rounded-lg border p-4">
              <h3 className="mb-1 text-sm font-semibold">Hardship evidence</h3>
              <p className="text-sm leading-relaxed">
                {brief.hardship_status === "recorded"
                  ? "Financial hardship is recorded in the case history. Confirm the customer’s current circumstances during review."
                  : brief.hardship_status === "possible"
                    ? "The available evidence suggests possible financial hardship. A reviewer must confirm it."
                    : "The available evidence does not establish financial hardship. This does not mean hardship is absent."}
              </p>
              {!!brief.recorded_hardship_cases?.length && (
                <div className="mt-3">
                  <p className="text-muted-foreground mb-1 text-xs">Recorded case references</p>
                  <SourceList sources={brief.recorded_hardship_cases} />
                </div>
              )}
            </div>
          )}
          <div className="bg-accent/50 rounded-lg border border-primary/15 p-4">
            <h3 className="text-accent-foreground mb-1 text-sm font-semibold">Overall recommendation</h3>
            <p className="leading-relaxed whitespace-pre-line">{brief.recommendation}</p>
            {brief.recommendation_reason && (
              <div className="mt-3 border-t border-primary/15 pt-3">
                <h3 className="text-accent-foreground mb-1 text-sm font-semibold">Why this recommendation</h3>
                <p className="text-sm leading-relaxed whitespace-pre-line">{brief.recommendation_reason}</p>
              </div>
            )}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Signals and evidence</CardTitle>
          <CardDescription>Each signal the brief relies on, with the record it came from.</CardDescription>
        </CardHeader>
        <CardContent>
          {brief.signals.length ? (
            <div className="rounded-lg border">
              <Table>
                <caption className="sr-only">Signals</caption>
                <TableHeader>
                  <TableRow className="hover:bg-transparent">
                    <TableHead scope="col">Signal</TableHead>
                    <TableHead scope="col">Value</TableHead>
                    <TableHead scope="col">Evidence</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {brief.signals.map((s, i) => (
                    <TableRow key={`${s.name}-${i}`}>
                      <TableCell className="align-top font-medium">{s.name}</TableCell>
                      <TableCell className="align-top">{displayValue(s.value)}</TableCell>
                      <TableCell className="text-muted-foreground max-w-[32rem] align-top break-words">
                        {displayValue(s.evidence)}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          ) : (
            <EmptyState title="No signals returned" />
          )}
        </CardContent>
      </Card>

      <div className="grid gap-6 lg:grid-cols-[1.4fr_1fr]">
        <Card>
          <CardHeader>
            <CardTitle>{draftTitle}</CardTitle>
            <CardDescription>
              {brief.contact_hold
                ? "For internal supervisor review only. This is not a message to send or read to the customer."
                : "Read-only here. Supervisors can edit it during review."}
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Label htmlFor="brief-draft" className="sr-only">
              {draftTitle}
            </Label>
            <Textarea id="brief-draft" readOnly value={brief.draft} className="bg-muted/40 min-h-40 leading-relaxed" />
          </CardContent>
        </Card>
        <div className="space-y-8">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Cpu className="text-muted-foreground size-4" aria-hidden /> Model
              </CardTitle>
            </CardHeader>
            <CardContent>
              <dl className="grid grid-cols-2 gap-4 text-sm">
                <div>
                  <dt className="text-muted-foreground text-sm">Name</dt>
                  <dd className="font-medium break-words">{brief.model.name}</dd>
                </div>
                <div>
                  <dt className="text-muted-foreground text-sm">Version</dt>
                  <dd className="font-medium break-words">{brief.model.version}</dd>
                </div>
              </dl>
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>Policy sources</CardTitle>
            </CardHeader>
            <CardContent>
              <SourceList sources={brief.policy_sources} empty="No policy sources cited." />
            </CardContent>
          </Card>
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Features used</CardTitle>
          <CardDescription>Feature-store values at generation time. Protected attributes are excluded.</CardDescription>
        </CardHeader>
        <CardContent>
          <KeyValueList data={brief.features} emptyTitle="No features returned" />
        </CardContent>
      </Card>

      <Button asChild variant="outline">
        <Link href="/reviews">
          Go to review queue <ArrowRight aria-hidden />
        </Link>
      </Button>
    </div>
  );
}

function BriefWorkspace() {
  const params = useSearchParams();
  const initial = params.get("customer") ?? "";
  const [customerId, setCustomerId] = useState(initial);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [brief, setBrief] = useState<Brief | null>(null);
  const resultRef = useRef<HTMLDivElement>(null);

  useEffect(() => setCustomerId(initial), [initial]);

  async function generate(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const id = customerId.trim();
    if (!id) return;
    setPending(true);
    setError(null);
    setBrief(null);
    try {
      const result = await api<Brief>("/briefs", { method: "POST", body: JSON.stringify({ customer_id: id }) });
      setBrief(result);
      requestAnimationFrame(() => resultRef.current?.focus());
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setPending(false);
    }
  }

  return (
    <>
      <Card className="mb-8">
        <CardContent>
          <form onSubmit={generate} className="flex flex-col gap-3 sm:flex-row sm:items-end">
            <div className="flex-1 space-y-2">
              <Label htmlFor="brief-customer">Customer ID</Label>
              <Input
                id="brief-customer"
                required
                autoComplete="off"
                className="font-mono"
                placeholder="Golden customer ID"
                value={customerId}
                onChange={(e) => setCustomerId(e.target.value)}
              />
            </div>
            <Button type="submit" disabled={pending || !customerId.trim()}>
              {pending ? <Loader2 className="animate-spin" aria-hidden /> : <Sparkles aria-hidden />}
              {pending ? "Preparing…" : "Prepare brief"}
            </Button>
          </form>
          <p className="text-muted-foreground mt-3 text-xs">
            Find IDs on the{" "}
            <Link href="/customers" className="underline underline-offset-4">
              Customers
            </Link>{" "}
            page. Agents can only prepare briefs for customers on their assigned cases.
          </p>
        </CardContent>
      </Card>

      <div ref={resultRef} tabIndex={-1} aria-live="polite" className="outline-none">
        {error && <ErrorState title="Brief not created" message={error} />}
        {brief && <BriefView brief={brief} />}
        {!brief && !error && !pending && (
          <EmptyState
            title="No brief yet"
            description="Enter a customer ID to prepare a call brief: what to do in order, the evidence and policy behind each step, and a draft message."
          />
        )}
      </div>
    </>
  );
}

export default function BriefsPage() {
  return (
    <>
      <PageHeader
        title="Agent brief"
        description="Prepare a call brief for one customer. The model only drafts; a supervisor reviews every draft before it can be used."
      />
      <RoleGate section="briefs">
        <Suspense fallback={null}>
          <BriefWorkspace />
        </Suspense>
      </RoleGate>
    </>
  );
}
