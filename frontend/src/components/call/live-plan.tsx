"use client";

import { Calculator, ChevronDown, CircleCheck, Scale, ShieldCheck } from "lucide-react";
import { ActionPlanCard } from "@/components/action-plan";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import type { Affordability, CalcOption, CallSession, Check } from "@/lib/call-types";
import { formatMoney } from "@/lib/call-outcomes";
import { cn } from "@/lib/utils";
import { CheckLine } from "./guided-call";

const ORDER: Record<Check["status"], number> = { block: 0, warn: 1, ok: 2 };

function Panel({ title, icon: Icon, children, aside }: { title: string; icon: typeof Scale; children: React.ReactNode; aside?: React.ReactNode }) {
  return (
    <section aria-label={title} className="bg-card rounded-xl border p-5 shadow-xs">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h3 className="flex items-center gap-2 font-semibold">
          <Icon className="text-primary size-4" aria-hidden /> {title}
        </h3>
        {aside}
      </div>
      {children}
    </section>
  );
}

export function ChecksPanel({ checks }: { checks: Check[] }) {
  const sorted = [...checks].sort((a, b) => ORDER[a.status] - ORDER[b.status]);
  const blocks = checks.filter((c) => c.status === "block").length;
  const warns = checks.filter((c) => c.status === "warn").length;
  return (
    <Panel
      title="Rule checks"
      icon={ShieldCheck}
      aside={
        checks.length > 0 && (
          <span className="flex gap-1.5">
            {blocks > 0 && <Badge variant="destructive">{blocks} blocking</Badge>}
            {warns > 0 && <Badge variant="review">{warns} to note</Badge>}
            {!blocks && !warns && <Badge variant="success">All clear</Badge>}
          </span>
        )
      }
    >
      {sorted.length ? (
        <ul className="space-y-1.5">
          {sorted.map((c) => (
            <CheckLine key={`${c.key}-${c.message}`} check={c} />
          ))}
        </ul>
      ) : (
        <p className="text-muted-foreground text-sm">Nothing to check yet. Checks appear as you record what happens on the call.</p>
      )}
    </Panel>
  );
}

const CALC_STATUS: Record<CalcOption["status"], { label: string; badge: "success" | "review" | "outline" }> = {
  likely_eligible: { label: "Likely eligible", badge: "success" },
  check: { label: "Check eligibility", badge: "review" },
  not_eligible: { label: "Not eligible", badge: "outline" },
};

/** Three bars on one shared scale: what they pay now, during the programme, after it ends. */
function PaymentSteps({ option, scale }: { option: CalcOption; scale: number }) {
  // A lasting change (same payment during and after) shows as two bars: before and from now on.
  const lasting = option.payment_during !== null && option.payment_during === option.payment_after;
  const bars = lasting
    ? [
        { label: "Now", value: option.payment_now, tone: "bg-muted-foreground/35" },
        { label: "From now on", value: option.payment_during, tone: "bg-primary" },
      ]
    : [
        { label: "Now", value: option.payment_now, tone: "bg-muted-foreground/35" },
        { label: option.months ? `For ${option.months} mo` : "During", value: option.payment_during, tone: "bg-primary" },
        { label: "After", value: option.payment_after, tone: "bg-primary/45" },
      ];
  return (
    <div className={cn("grid gap-3", lasting ? "grid-cols-2" : "grid-cols-3")} role="group" aria-label={`Monthly payment for ${option.name}`}>
      {bars.map((bar) => {
        const pct = bar.value !== null && scale > 0 ? Math.max(3, (bar.value / scale) * 100) : 0;
        return (
          <div key={bar.label} className="flex min-w-0 flex-col">
            <span className="text-sm font-semibold tabular-nums">{bar.value === null ? "—" : formatMoney(bar.value)}</span>
            <div className="bg-muted/70 mt-1 flex h-14 items-end overflow-hidden rounded-md" aria-hidden>
              <div className={cn("w-full rounded-md transition-[height] duration-500 motion-reduce:transition-none", bar.tone)} style={{ height: `${pct}%` }} />
            </div>
            <span className="text-muted-foreground mt-1 truncate text-xs">{bar.label}</span>
          </div>
        );
      })}
    </div>
  );
}

function OptionCard({ option, scale, selected, onChoose }: { option: CalcOption; scale: number; selected: boolean; onChoose: () => void }) {
  const status = CALC_STATUS[option.status];
  const facts = [
    option.monthly_saving !== null && ["Saves per month", formatMoney(option.monthly_saving)],
    option.deferred_amount !== null && ["Moved to the end", formatMoney(option.deferred_amount)],
    option.interest_saving !== null && [option.interest_saving >= 0 ? "Interest saved" : "Extra interest", formatMoney(Math.abs(option.interest_saving))],
    option.one_time_amount !== null && ["One-time payment", formatMoney(option.one_time_amount)],
    option.months !== null && option.payment_during !== null && option.payment_during === option.payment_after && ["New term", `${option.months} months`],
  ].filter((f): f is [string, string] => !!f);
  const disabled = option.status === "not_eligible";
  return (
    <li
      className={cn(
        "rounded-lg border p-4 transition-colors",
        selected ? "border-primary bg-accent/50 ring-primary/25 ring-2" : "bg-background",
        disabled && "opacity-75",
      )}
    >
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="leading-snug font-medium">{option.name}</p>
          <p className="text-muted-foreground font-mono text-[0.7rem]">
            {option.program_id} v{option.version}
          </p>
        </div>
        <Badge variant={status.badge}>{status.label}</Badge>
      </div>
      <div className="mt-3">
        <PaymentSteps option={option} scale={scale} />
      </div>
      {facts.length > 0 && (
        <dl className="mt-3 grid grid-cols-2 gap-x-3 gap-y-1.5 text-sm">
          {facts.map(([k, v]) => (
            <div key={k}>
              <dt className="text-muted-foreground text-xs">{k}</dt>
              <dd className="font-medium tabular-nums">{v}</dd>
            </div>
          ))}
        </dl>
      )}
      {option.note && <p className="text-muted-foreground mt-2 text-xs leading-relaxed">{option.note}</p>}
      {option.reasons.length > 0 && <p className="text-review-foreground mt-1.5 text-xs leading-relaxed">{option.reasons.join("; ")}</p>}
      <div className="mt-3 flex flex-wrap items-center justify-between gap-2 border-t pt-3">
        <span className="text-muted-foreground text-xs">Approver: {option.approver.replace(/_/g, " ")}</span>
        {!disabled && (
          <Button type="button" size="sm" variant={selected ? "default" : "outline"} aria-pressed={selected} onClick={onChoose}>
            {selected ? (
              <>
                <CircleCheck aria-hidden /> Chosen
              </>
            ) : (
              "Choose"
            )}
          </Button>
        )}
      </div>
    </li>
  );
}

export function CalculatorPanel({
  calculator,
  selected,
  onChoose,
  disabled,
}: {
  calculator: CallSession["calculator"];
  selected: string | null;
  onChoose: (programId: string | null) => void;
  disabled: boolean;
}) {
  const { account, options } = calculator;
  const values = options.flatMap((o) => [o.payment_now, o.payment_during, o.payment_after]).filter((v): v is number => typeof v === "number");
  const scale = Math.max(0, ...values);
  const shown = options.filter((o) => o.status !== "not_eligible");
  const hidden = options.filter((o) => o.status === "not_eligible");
  const apr = account.apr === null ? null : account.apr < 1 ? account.apr * 100 : account.apr;
  return (
    <Panel title="Hardship options" icon={Calculator}>
      <p className="text-muted-foreground mb-3 text-xs leading-relaxed">
        {account.product.replace(/_/g, " ")}: balance {formatMoney(account.balance)}, regular payment {formatMoney(account.regular_payment)}
        {apr !== null && `, APR ${apr.toFixed(2)}%`}
        {account.remaining_term_months !== null && `, ${account.remaining_term_months} months left`}.{" "}
        <span className="font-mono">{account.source}</span>
      </p>
      {options.length === 0 ? (
        <p className="text-muted-foreground text-sm">No programme applies yet. Options appear when hardship is recorded or the customer states it.</p>
      ) : (
        <fieldset disabled={disabled} className="min-w-0">
          <legend className="sr-only">Choose a hardship programme</legend>
          {shown.length ? (
            <ul className="space-y-2.5">
              {shown.map((o) => (
                <OptionCard
                  key={o.program_id}
                  option={o}
                  scale={scale}
                  selected={selected === o.program_id}
                  onChoose={() => onChoose(selected === o.program_id ? null : o.program_id)}
                />
              ))}
            </ul>
          ) : (
            <p className="text-sm">No programme passes the recorded rules.</p>
          )}
          {hidden.length > 0 && (
            <Collapsible className="mt-2">
              <CollapsibleTrigger className="text-muted-foreground hover:text-foreground group flex items-center gap-1 text-sm underline-offset-4 hover:underline">
                <ChevronDown className="size-4 transition-transform group-data-[state=open]:rotate-180" aria-hidden /> {hidden.length} not eligible, with reasons
              </CollapsibleTrigger>
              <CollapsibleContent>
                <ul className="mt-2 space-y-2.5">
                  {hidden.map((o) => (
                    <OptionCard key={o.program_id} option={o} scale={scale} selected={false} onChoose={() => undefined} />
                  ))}
                </ul>
              </CollapsibleContent>
            </Collapsible>
          )}
          <p className="text-muted-foreground mt-3 text-xs">Figures follow the programme rules. The named approver confirms eligibility.</p>
        </fieldset>
      )}
    </Panel>
  );
}

export function AffordabilityPanel({ affordability: a, promise }: { affordability: Affordability; promise: number | null }) {
  const share = a.promise_share_of_disposable;
  const pct = share === null ? null : Math.round(share * 100);
  const tone = share === null ? "bg-primary" : share > 1 ? "bg-destructive" : share > 0.5 ? "bg-review" : "bg-primary";
  const rows = [
    ["Income", a.monthly_income],
    ["Housing", a.housing],
    ["Other obligations", a.monthly_obligations],
  ] as const;
  return (
    <Panel title="Affordability" icon={Scale} aside={!a.verified && <Badge variant="review">Declared, not verified</Badge>}>
      {a.disposable === null ? (
        <p className="text-muted-foreground text-sm">Ask for monthly income and expenses to check whether a payment is affordable.</p>
      ) : (
        <>
          <dl className="grid grid-cols-2 gap-x-3 gap-y-1.5 text-sm sm:grid-cols-4">
            {rows.map(([k, v]) => (
              <div key={k}>
                <dt className="text-muted-foreground text-xs">{k}</dt>
                <dd className="tabular-nums">{formatMoney(v)}</dd>
              </div>
            ))}
            <div>
              <dt className="text-muted-foreground text-xs">Left each month</dt>
              <dd className="font-semibold tabular-nums">{formatMoney(a.disposable)}</dd>
            </div>
          </dl>
          <div className="mt-4">
            <div
              className="bg-muted relative h-3 overflow-hidden rounded-full"
              role="meter"
              aria-label="Promise as a share of money left each month"
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={pct === null ? 0 : Math.min(pct, 100)}
              aria-valuetext={pct === null ? "No promise yet" : `${pct}%`}
            >
              <div className={cn("h-full rounded-full transition-[width] duration-500 motion-reduce:transition-none", tone)} style={{ width: `${pct === null ? 0 : Math.min(100, pct)}%` }} />
            </div>
            <p className="mt-1.5 text-sm">
              {pct === null || promise === null ? (
                <span className="text-muted-foreground">Record a promise to compare it with what is left each month.</span>
              ) : (
                <>
                  Promise of <strong>{formatMoney(promise)}</strong> is <strong className={cn(share! > 1 ? "text-destructive" : share! > 0.5 && "text-review-foreground")}>{pct}%</strong> of
                  what is left each month.
                  {share! > 1 && " It is more than they have left."}
                </>
              )}
            </p>
          </div>
        </>
      )}
      <p className="text-muted-foreground mt-2 text-xs">Source: {a.source}</p>
    </Panel>
  );
}

export function LivePlan({
  session,
  changed,
  selectedProgramme,
  onChoose,
  disabled,
  promise,
}: {
  session: CallSession;
  changed: ReadonlySet<string>;
  selectedProgramme: string | null;
  onChoose: (programId: string | null) => void;
  disabled: boolean;
  promise: number | null;
}) {
  return (
    <div className="space-y-4">
      <ActionPlanCard plan={session.plan} compact changed={changed} />
      <ChecksPanel checks={session.checks} />
      <CalculatorPanel calculator={session.calculator} selected={selectedProgramme} onChoose={onChoose} disabled={disabled} />
      <AffordabilityPanel affordability={session.affordability} promise={promise} />
    </div>
  );
}
