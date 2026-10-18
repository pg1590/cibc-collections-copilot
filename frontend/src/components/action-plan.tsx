"use client";

import { AlertTriangle, Ban, CheckCircle2, ChevronDown, Clock, ListChecks, PlayCircle } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { PolicyLink } from "@/components/policy-link";
import type { ActionPlan, PlanStep, Programme, StepStatus } from "@/lib/plan-types";
import { cn } from "@/lib/utils";

const STATUS: Record<StepStatus, { label: string; icon: typeof Ban; tone: string; badge: "destructive" | "default" | "review" | "outline" | "success" }> = {
  stop: { label: "Stop", icon: Ban, tone: "border-destructive/40 bg-destructive/5", badge: "destructive" },
  action: { label: "Do", icon: PlayCircle, tone: "border-primary/30 bg-accent/40", badge: "default" },
  caution: { label: "Careful", icon: AlertTriangle, tone: "border-review/40 bg-review-soft/50", badge: "review" },
  wait: { label: "Wait", icon: Clock, tone: "bg-muted/40", badge: "outline" },
  clear: { label: "Checked", icon: CheckCircle2, tone: "bg-card", badge: "success" },
};

const PROGRAMME_STATUS: Record<Programme["status"], { label: string; badge: "success" | "review" | "outline" }> = {
  likely_eligible: { label: "Likely eligible", badge: "success" },
  check: { label: "Check", badge: "review" },
  not_eligible: { label: "Not eligible", badge: "outline" },
};

function Step({ step, changed = false, compact = false }: { step: PlanStep; changed?: boolean; compact?: boolean }) {
  const s = STATUS[step.status];
  const Icon = s.icon;
  // In compact mode a step that is already checked shows only its title.
  const brief = compact && step.status === "clear";
  return (
    <li className={cn("rounded-lg border", compact ? "p-3" : "p-4", s.tone, changed && "motion-safe:animate-plan-flash")}>
      <div className="flex items-start gap-3">
        <span className="bg-background text-muted-foreground mt-0.5 flex size-6 shrink-0 items-center justify-center rounded-full border text-xs font-semibold tabular-nums">
          {step.order}
        </span>
        <div className="min-w-0 flex-1 space-y-1.5">
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant={s.badge}>
              <Icon aria-hidden /> {s.label}
            </Badge>
            <h4 className="font-semibold leading-snug">{step.title}</h4>
            {changed && <span className="text-primary text-xs font-medium">Updated</span>}
          </div>
          {!brief && <p className="text-sm leading-relaxed">{step.detail}</p>}
          {!brief && (step.policy.length > 0 || (!compact && step.evidence.length > 0)) && (
            <div className="flex flex-wrap gap-1.5 pt-1">
              {step.policy.map((p) => (
                <PolicyLink key={p} text={p} />
              ))}
              {!compact && step.evidence.map((e) => (
                <span key={e} className="bg-muted/70 text-muted-foreground rounded px-1.5 py-0.5 font-mono text-[0.75rem] break-all">
                  {e}
                </span>
              ))}
            </div>
          )}
        </div>
      </div>
    </li>
  );
}

function Programmes({ items }: { items: Programme[] }) {
  if (!items.length) return null;
  const shown = items.filter((p) => p.status !== "not_eligible");
  const hidden = items.filter((p) => p.status === "not_eligible");
  const row = (p: Programme) => (
    <li key={`${p.program_id}-${p.version}`} className="flex flex-col gap-1 border-b py-3 last:border-b-0 sm:flex-row sm:items-start sm:gap-4">
      <div className="min-w-0 flex-1">
        <p className="font-medium">
          {p.name} <span className="text-muted-foreground font-mono text-xs">{p.program_id} v{p.version}</span>
        </p>
        <p className="text-muted-foreground text-sm">{p.description}</p>
        {p.reasons.length > 0 && <p className="text-sm">{p.reasons.join("; ")}</p>}
        {p.missing_inputs.length > 0 && <p className="text-review-foreground text-sm">Needs: {p.missing_inputs.join("; ")}</p>}
      </div>
      <div className="flex shrink-0 flex-wrap items-center gap-2 sm:flex-col sm:items-end">
        <Badge variant={PROGRAMME_STATUS[p.status].badge}>{PROGRAMME_STATUS[p.status].label}</Badge>
        <span className="text-muted-foreground text-xs">Approver: {p.approver.replace(/_/g, " ")}</span>
      </div>
    </li>
  );
  return (
    <section aria-label="Hardship programmes" className="rounded-lg border p-4">
      <h4 className="mb-1 text-sm font-semibold">Hardship programmes checked against the recorded rules</h4>
      <p className="text-muted-foreground mb-2 text-xs">
        Versions effective on the snapshot date. Suggestions only; the named approver confirms eligibility.
      </p>
      {shown.length ? <ul>{shown.map(row)}</ul> : <p className="text-sm">No programme passes the recorded rules.</p>}
      {hidden.length > 0 && (
        <Collapsible>
          <CollapsibleTrigger className="text-muted-foreground hover:text-foreground mt-2 flex items-center gap-1 text-sm underline-offset-4 hover:underline">
            <ChevronDown className="size-4" aria-hidden /> {hidden.length} not eligible, with reasons
          </CollapsibleTrigger>
          <CollapsibleContent>
            <ul className="mt-1">{hidden.map(row)}</ul>
          </CollapsibleContent>
        </Collapsible>
      )}
    </section>
  );
}

/** `changed` lists step keys to mark as just updated (Live Call Mode recomputes the plan as the call goes). */
export function ActionPlanCard({
  plan,
  compact = false,
  changed,
}: {
  plan: ActionPlan;
  compact?: boolean;
  changed?: ReadonlySet<string>;
}) {
  return (
    <Card className="border-primary/25">
      <CardHeader>
        <CardDescription>
          Case <span className="font-mono">{plan.case_id}</span> · as of snapshot {plan.snapshot_date}
          {plan.other_open_cases?.length ? ` · also open: ${plan.other_open_cases.join(", ")}` : ""}
        </CardDescription>
        <CardTitle className="flex items-center gap-2 text-lg">
          <ListChecks className="text-primary size-5" aria-hidden /> What to do, in order
        </CardTitle>
        <p className="text-sm">
          <span className="text-muted-foreground">Next action: </span>
          <strong>{plan.next_action}</strong>
        </p>
      </CardHeader>
      <CardContent className="space-y-4">
        <ol className="space-y-2.5">
          {plan.steps.map((step) => (
            <Step key={`${step.order}-${step.key}`} step={step} changed={changed?.has(step.key)} compact={compact} />
          ))}
        </ol>
        {!compact && <Programmes items={plan.programmes} />}
        <p className="text-muted-foreground text-xs leading-relaxed">{plan.note}</p>
      </CardContent>
    </Card>
  );
}
