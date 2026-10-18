"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { ArrowLeft, ArrowDown, Ban, CheckCircle2, CircleAlert, Loader2, PhoneCall } from "lucide-react";
import { CustomerPanel } from "@/components/call/customer-panel";
import { EMPTY_DRAFTS, GuidedCall, type CallDrafts } from "@/components/call/guided-call";
import { LivePlan } from "@/components/call/live-plan";
import { NotesExtract } from "@/components/call/notes-extract";
import { WrapUpPanel } from "@/components/call/wrap-up";
import { RoleGate } from "@/components/role-gate";
import { ErrorState } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { LeaveGuardContext } from "@/lib/leave-guard";
import { EMPTY_OUTCOMES, type CallSession, type CallStage, type ExtractProposal, type Outcomes, type SubmitResponse } from "@/lib/call-types";
import { applyProposal, canonical } from "@/lib/call-outcomes";
import { useCallSession } from "@/lib/use-call-session";
import { cn } from "@/lib/utils";

function safeDecode(value: string) {
  try {
    return decodeURIComponent(value);
  } catch {
    return value;
  }
}

const STAGES: { key: Exclude<CallStage, "blocked">; label: string }[] = [
  { key: "pre_call", label: "Before the call" },
  { key: "verification", label: "Verify" },
  { key: "conversation", label: "Conversation" },
  { key: "wrap_up", label: "Wrap-up" },
];

function StageRail({ stage, skipTalk }: { stage: CallStage; skipTalk: boolean }) {
  if (stage === "blocked") {
    return (
      <p className="bg-destructive text-destructive-foreground inline-flex items-center gap-2 rounded-full px-3 py-1 text-sm font-medium">
        <Ban className="size-4" aria-hidden /> Contact blocked
      </p>
    );
  }
  const current = STAGES.findIndex((s) => s.key === stage);
  return (
    <ol className="flex flex-wrap items-center gap-x-1 gap-y-1 text-sm" aria-label="Call stage">
      {STAGES.map((s, i) => {
        // When nobody verifiable answered, verification and conversation are skipped rather than done.
        const skipped = skipTalk && (s.key === "verification" || s.key === "conversation");
        return (
        <li key={s.key} className="flex items-center gap-1" aria-current={i === current ? "step" : undefined}>
          {i > 0 && <span className={cn("hidden h-px w-6 sm:block", i <= current ? "bg-primary" : "bg-border")} aria-hidden />}
          <span
            className={cn(
              "rounded-full px-2.5 py-1 font-medium whitespace-nowrap",
              i < current && !skipped && "text-primary",
              i === current && "bg-primary text-primary-foreground",
              (i > current || skipped) && "text-muted-foreground",
              skipped && "line-through decoration-1",
            )}
          >
            {i < current && !skipped && <CheckCircle2 className="mr-1 inline size-3.5 align-[-2px]" aria-hidden />}
            {s.label}
            {skipped && <span className="sr-only"> (skipped)</span>}
          </span>
        </li>
        );
      })}
    </ol>
  );
}

function Updating({ active }: { active: boolean }) {
  return (
    <span className={cn("text-muted-foreground inline-flex items-center gap-1.5 text-xs transition-opacity", active ? "opacity-100" : "opacity-0")} aria-hidden={!active}>
      <Loader2 className="size-3.5 animate-spin" aria-hidden /> Updating…
    </span>
  );
}

/** Keys of plan steps that are new or changed between two results. */
function changedSteps(prev: CallSession | null, next: CallSession): Set<string> {
  if (!prev) return new Set();
  const before = new Map(prev.plan.steps.map((s) => [s.key, `${s.status}|${s.title}|${s.detail}`]));
  return new Set(next.plan.steps.filter((s) => before.get(s.key) !== `${s.status}|${s.title}|${s.detail}`).map((s) => s.key));
}

function PageSkeleton() {
  return (
    <div role="status" aria-live="polite" className="grid gap-5 wide:grid-cols-[15rem_minmax(0,1fr)_25rem] lg:grid-cols-2">
      <span className="sr-only">Starting the call…</span>
      <Skeleton className="h-64 w-full lg:col-span-2 wide:col-span-1" />
      <div className="space-y-4">
        <Skeleton className="h-36 w-full" />
        <Skeleton className="h-56 w-full" />
      </div>
      <div className="space-y-4">
        <Skeleton className="h-80 w-full" />
        <Skeleton className="h-40 w-full" />
      </div>
    </div>
  );
}

function CallWorkspace({ customerId }: { customerId: string }) {
  const [outcomes, setOutcomes] = useState<Outcomes>(EMPTY_OUTCOMES);
  const [drafts, setDrafts] = useState<CallDrafts>(EMPTY_DRAFTS);
  const [submitted, setSubmitted] = useState<SubmitResponse | null>(null);
  const call = useCallSession(customerId, outcomes);
  const session = call.data;

  // Highlight plan steps that changed with the latest recompute, and announce the new next action.
  const previous = useRef<CallSession | null>(null);
  const [changed, setChanged] = useState<ReadonlySet<string>>(new Set());
  const [announcement, setAnnouncement] = useState("");
  useEffect(() => {
    if (!session) return;
    const prev = previous.current;
    previous.current = session;
    if (!prev) return;
    const keys = changedSteps(prev, session);
    setChanged(keys);
    const blocks = session.checks.filter((c) => c.status === "block").length;
    if (keys.size || prev.plan.next_action !== session.plan.next_action || prev.checks.length !== session.checks.length) {
      setAnnouncement(`Plan updated. Next action: ${session.plan.next_action}.${blocks ? ` ${blocks} blocking check${blocks === 1 ? "" : "s"}.` : ""}`);
    }
    const timer = window.setTimeout(() => setChanged(new Set()), 2000);
    return () => window.clearTimeout(timer);
  }, [session]);

  // Adopt the server-normalised outcomes when they differ and the agent has not changed anything since.
  const adopted = useRef<string | null>(null);
  useEffect(() => {
    const server = session?.outcomes;
    if (!server || call.requested === null) return;
    const mine = canonical(outcomes);
    if (canonical(JSON.parse(call.requested)) !== mine) return;
    const theirs = canonical(server);
    if (theirs === mine || adopted.current === theirs) return;
    adopted.current = theirs;
    setOutcomes(server);
  }, [session, call.requested, outcomes]);

  const update = useCallback((fn: (o: Outcomes) => Outcomes) => setOutcomes((o) => fn(o)), []);

  const accept = useCallback(
    (p: ExtractProposal) => {
      const focus = (id: string) => window.setTimeout(() => document.getElementById(id)?.focus(), 50);
      if (p.field === "callback" && (p.value === null || typeof p.value !== "object")) {
        focus("callback-date");
        return;
      }
      if (p.field === "promise" && p.value && typeof p.value === "object") {
        const v = p.value as { amount?: number | null; date?: string | null };
        const amount = typeof v.amount === "number" ? v.amount : null;
        const date = v.date ?? "";
        setDrafts((d) => ({ ...d, promise: { amount, date } }));
        setOutcomes((o) => ({ ...o, promise: amount !== null && date ? { amount, date } : null }));
        if (!date) focus("promise-date");
        return;
      }
      if (p.field === "callback") {
        const v = p.value as { date?: string; time?: string };
        setDrafts((d) => ({ ...d, callback: { date: v.date ?? "", time: v.time ?? "" } }));
        if (v.date && v.time) setOutcomes((o) => ({ ...o, callback: { date: v.date!, time: v.time! } }));
        else focus(v.date ? "callback-time" : "callback-date");
        return;
      }
      setOutcomes((o) => applyProposal(o, p.field, p.value));
    },
    [],
  );

  if (!session) {
    if (call.error) return <ErrorState title="Could not start the call" message={call.error} onRetry={call.retry} />;
    return <PageSkeleton />;
  }

  const blocked = session.stage === "blocked";
  const blocking = session.wrap_up.blocking.length;
  const ready = session.wrap_up.ready_to_submit;
  // Outcomes live only in this page, so policy links ask before leaving an unsubmitted call.
  const unsaved =
    !submitted && (JSON.stringify(outcomes) !== JSON.stringify(EMPTY_OUTCOMES) || JSON.stringify(drafts) !== JSON.stringify(EMPTY_DRAFTS));

  return (
    <LeaveGuardContext.Provider value={unsaved ? "Leave this call? Outcomes you've recorded but not submitted will be lost." : null}>
      <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
        <StageRail stage={session.stage} skipTalk={!!outcomes.reached && outcomes.reached !== "customer"} />
        <Updating active={call.loading} />
      </div>

      <p className="sr-only" aria-live="polite" aria-atomic="true">
        {announcement}
      </p>

      <div className="grid items-start gap-5 lg:grid-cols-2 wide:grid-cols-[15rem_minmax(0,1fr)_25rem]">
        <aside aria-label="Customer" className="min-w-0 lg:col-span-2 wide:sticky wide:top-20 wide:col-span-1">
          <CustomerPanel session={session} />
        </aside>

        <div className="min-w-0">
          <GuidedCall
            session={session}
            outcomes={outcomes}
            update={update}
            disabled={blocked || !!submitted}
            drafts={drafts}
            setDrafts={setDrafts}
            notes={<NotesExtract customerId={customerId} onAccept={accept} />}
          />
        </div>

        <aside
          aria-label="Live plan"
          aria-busy={call.loading}
          className="min-w-0 space-y-3 wide:sticky wide:top-20 wide:max-h-[calc(100dvh-10rem)] wide:overflow-y-auto wide:pr-1 wide:pb-2"
        >
          <div className="flex items-center justify-between gap-2">
            <h2 className="text-lg font-semibold">Live plan</h2>
            <Updating active={call.loading} />
          </div>
          {call.error && <ErrorState title="Could not update the plan" message={`${call.error} Showing the last result.`} onRetry={call.retry} />}
          <div className={cn("transition-opacity", call.loading && "opacity-80")}>
            <LivePlan
              session={session}
              changed={changed}
              selectedProgramme={outcomes.programme}
              onChoose={(programme) => setOutcomes((o) => ({ ...o, programme }))}
              disabled={blocked || !session.can_discuss_debt || !!submitted}
              promise={outcomes.promise?.amount ?? null}
            />
          </div>
        </aside>
      </div>

      <section id="wrap-up" aria-labelledby="wrap-up-title" tabIndex={-1} className="bg-card mt-6 scroll-mt-24 rounded-xl border p-5 shadow-xs outline-none sm:p-6">
        <div className="mb-4 flex flex-wrap items-baseline justify-between gap-2">
          <h2 id="wrap-up-title" className="text-lg font-semibold">
            Wrap-up
          </h2>
          <p className="text-muted-foreground text-sm">Goes to a supervisor for review.</p>
        </div>
        <WrapUpPanel
          key={customerId}
          customerId={customerId}
          wrapUp={session.wrap_up}
          outcomes={outcomes}
          stale={call.loading}
          submitted={submitted}
          onSubmitted={setSubmitted}
        />
      </section>

      {!submitted && (
        <div className="bg-background/95 sticky bottom-0 z-10 -mx-4 mt-6 flex flex-wrap items-center justify-between gap-2 border-t px-4 py-3 backdrop-blur sm:-mx-8 sm:px-8">
          <p className="flex min-w-0 items-center gap-2 text-sm">
            {ready ? (
              <>
                <CheckCircle2 className="text-success size-4 shrink-0" aria-hidden /> <span>Ready to submit for review</span>
              </>
            ) : (
              <>
                <CircleAlert className={cn("size-4 shrink-0", blocked ? "text-destructive" : "text-review")} aria-hidden />
                <span>
                  {blocked
                    ? "No call can be made to this customer"
                    : blocking
                      ? `${blocking} item${blocking === 1 ? "" : "s"} to resolve before submitting`
                      : "Record the call outcome to submit"}
                </span>
              </>
            )}
          </p>
          <Button
            type="button"
            size="sm"
            variant={ready ? "default" : "outline"}
            onClick={() => {
              const el = document.getElementById("wrap-up");
              el?.scrollIntoView({ behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
              el?.focus({ preventScroll: true });
            }}
          >
            <ArrowDown aria-hidden /> Go to wrap-up
          </Button>
        </div>
      )}
    </LeaveGuardContext.Provider>
  );
}

export default function CallPage() {
  const params = useParams<{ id: string }>();
  const id = safeDecode(params.id);
  return (
    <>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
        <div className="min-w-0">
          <Button asChild variant="ghost" size="sm" className="-ml-2">
            <Link href={`/customers/${encodeURIComponent(id)}`}>
              <ArrowLeft aria-hidden /> Customer {id}
            </Link>
          </Button>
          <h1 className="mt-1 flex items-center gap-2 text-2xl font-semibold sm:text-[1.75rem]">
            <PhoneCall className="text-primary size-6" aria-hidden /> Live call
          </h1>
        </div>
        <p className="text-muted-foreground max-w-md text-sm leading-relaxed">
          The plan follows the bank&rsquo;s rules and updates as you record the call. You confirm every step. Nothing is sent to the customer.
        </p>
      </div>
      <RoleGate section="call">
        <CallWorkspace key={id} customerId={id} />
      </RoleGate>
    </>
  );
}
