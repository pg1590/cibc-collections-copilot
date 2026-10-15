"use client";

import { useEffect, useId, useState } from "react";
import { AlertTriangle, Ban, CheckCircle2, Circle, Lock, PhoneMissed, ShieldAlert, Square, SquareCheck, User, UserX, Voicemail, X } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { CallSession, Check, Outcomes, Reached } from "@/lib/call-types";
import { DISPUTE_TYPE_LABEL, HARDSHIP_REASON_LABEL, REACHED_LABEL, REPRESENTATIVE_LABEL } from "@/lib/call-outcomes";
import { cn } from "@/lib/utils";

type Update = (fn: (o: Outcomes) => Outcomes) => void;

export function CallStep({
  n,
  title,
  hint,
  children,
  id,
  done = false,
}: {
  n: number;
  title: string;
  hint?: React.ReactNode;
  children: React.ReactNode;
  id?: string;
  done?: boolean;
}) {
  const headingId = useId();
  return (
    <section id={id} aria-labelledby={headingId} className="bg-card rounded-xl border p-5 shadow-xs scroll-mt-24">
      <div className="mb-4 flex items-start gap-3">
        <span
          className={cn(
            "flex size-7 shrink-0 items-center justify-center rounded-full border text-sm font-semibold tabular-nums",
            done ? "border-primary bg-primary text-primary-foreground" : "bg-background text-muted-foreground",
          )}
          aria-hidden
        >
          {done ? <CheckCircle2 className="size-4" /> : n}
        </span>
        <div className="min-w-0">
          <h3 id={headingId} className="leading-tight font-semibold">
            <span className="sr-only">Step {n}: </span>
            {title}
          </h3>
          {hint && <p className="text-muted-foreground mt-0.5 text-sm leading-snug">{hint}</p>}
        </div>
      </div>
      {children}
    </section>
  );
}

export const CHECK_STYLE: Record<Check["status"], { icon: typeof Ban; text: string; box: string; label: string }> = {
  ok: { icon: CheckCircle2, text: "text-success", box: "border-success/25 bg-success-soft/60", label: "OK" },
  warn: { icon: AlertTriangle, text: "text-review-foreground", box: "border-review/30 bg-review-soft/70", label: "Warning" },
  block: { icon: Ban, text: "text-destructive", box: "border-destructive/30 bg-destructive/5", label: "Blocked" },
};

export function CheckLine({ check }: { check: Check }) {
  const s = CHECK_STYLE[check.status];
  const Icon = s.icon;
  return (
    <li className={cn("flex items-start gap-2 rounded-md border px-3 py-2 text-sm", s.box)}>
      <Icon className={cn("mt-0.5 size-4 shrink-0", s.text)} aria-hidden />
      <div className="min-w-0">
        <span className="sr-only">{s.label}: </span>
        <span className={cn(check.status !== "ok" && "font-medium", s.text)}>{check.message}</span>
        {check.policy.length > 0 && <span className="text-muted-foreground ml-1.5 font-mono text-[0.75rem] break-words">{check.policy.join(", ")}</span>}
      </div>
    </li>
  );
}

function InlineChecks({ checks, prefix }: { checks: Check[]; prefix: string }) {
  const items = checks.filter((c) => c.key.startsWith(prefix));
  if (!items.length) return null;
  return (
    <ul className="mt-3 space-y-1.5" aria-label="Rule checks for this entry">
      {items.map((c) => (
        <CheckLine key={`${c.key}-${c.message}`} check={c} />
      ))}
    </ul>
  );
}

const REACHED_ICON: Record<Reached, typeof User> = { customer: User, third_party: UserX, no_answer: PhoneMissed, voicemail: Voicemail };

function ReachedStep({ outcomes, update }: { outcomes: Outcomes; update: Update }) {
  const name = useId();
  return (
    <CallStep n={1} title="Who answered?" hint="Pick one as soon as someone picks up." done={outcomes.reached !== null}>
      <div role="radiogroup" aria-label="Who answered" className="grid grid-cols-2 gap-2">
        {(Object.keys(REACHED_LABEL) as Reached[]).map((value) => {
          const Icon = REACHED_ICON[value];
          const checked = outcomes.reached === value;
          return (
            <label
              key={value}
              className={cn(
                "has-focus-visible:ring-ring/40 flex cursor-pointer items-center gap-2.5 rounded-lg border px-3 py-2.5 text-sm font-medium transition-colors has-focus-visible:ring-[3px]",
                checked ? "border-primary bg-accent text-accent-foreground" : "bg-background hover:border-primary/40",
              )}
            >
              <input
                type="radio"
                name={name}
                value={value}
                checked={checked}
                onChange={() => update((o) => ({ ...o, reached: value }))}
                className="sr-only"
              />
              <Icon className={cn("size-4 shrink-0", checked ? "text-primary" : "text-muted-foreground")} aria-hidden />
              {REACHED_LABEL[value]}
            </label>
          );
        })}
      </div>
      {(outcomes.reached === "third_party" || outcomes.reached === "voicemail") && (
        <div role="note" className="border-review/30 bg-review-soft text-review-foreground mt-3 flex gap-2 rounded-lg border p-3 text-sm">
          <ShieldAlert className="mt-0.5 size-4 shrink-0" aria-hidden />
          <p>
            <strong>No debt details to third parties.</strong> Leave only your first name and a callback number. Do not mention
            the debt, the amount or the collections team. <span className="font-mono text-[0.75rem]">POL-COLL-001 v3.0 §5.4</span>
          </p>
        </div>
      )}
      {outcomes.reached === "no_answer" && (
        <p className="text-muted-foreground mt-3 text-sm">The attempt still counts toward the 7-day contact limit. Wrap up and submit the attempt.</p>
      )}
    </CallStep>
  );
}

const SCRIPT_LABEL: Record<string, string> = {
  recording_notice: "Recording notice",
  identity_verified: "Verify identity",
  french: "Speak French",
  vulnerable: "Vulnerable-customer approach",
  purpose: "State the purpose",
  listen: "Listen for hardship",
  agree: "Agree and read back",
  close: "Close the call",
};

const SCRIPT_FIELD: { match: RegExp; field: "recording_notice" | "identity_verified" }[] = [
  { match: /^recording/i, field: "recording_notice" },
  { match: /^identity/i, field: "identity_verified" },
];

const fieldFor = (key: string) => SCRIPT_FIELD.find((f) => f.match.test(key))?.field;
const scriptLabel = (key: string) => SCRIPT_LABEL[key] ?? key.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase());

function ChecklistStep({ session, outcomes, update }: { session: CallSession; outcomes: Outcomes; update: Update }) {
  const reachedCustomer = outcomes.reached === "customer";
  const required = session.script.filter((s) => s.required);
  const allDone = required.length > 0 && required.every((s) => s.done);
  const guide = session.script.filter((item) => !item.required && !fieldFor(item.key));
  return (
    <CallStep
      n={2}
      title="Compliance checklist"
      hint={reachedCustomer ? "Read each line, then tick it. Debt talk unlocks once identity is verified." : "Starts once you reach the customer."}
      done={allDone && session.can_discuss_debt}
    >
      {session.script.length === 0 ? (
        <p className="text-muted-foreground text-sm">No script lines for this call.</p>
      ) : (
        <ul className="space-y-2">
          {session.script.filter((item) => item.required || fieldFor(item.key)).map((item) => {
            const field = fieldFor(item.key);
            const done = field ? outcomes[field] : item.done;
            const box = (
              <>
                {field ? (
                  done ? <SquareCheck className="text-primary mt-0.5 size-5 shrink-0" aria-hidden /> : <Square className="text-muted-foreground mt-0.5 size-5 shrink-0" aria-hidden />
                ) : done ? (
                  <CheckCircle2 className="text-primary mt-0.5 size-5 shrink-0" aria-hidden />
                ) : (
                  <Circle className="text-muted-foreground/60 mt-0.5 size-5 shrink-0" aria-hidden />
                )}
                <span className="min-w-0 flex-1">
                  <span className="flex flex-wrap items-center gap-1.5">
                    <span className="text-sm font-medium">{scriptLabel(item.key)}</span>
                    {item.required && <Badge variant="outline" className="text-[0.75rem]">Required</Badge>}
                    {!field && item.done && <span className="text-primary text-xs font-medium">Done</span>}
                  </span>
                  <span className="text-foreground/85 mt-1 block text-sm leading-relaxed">{item.text}</span>
                  {item.policy.length > 0 && <span className="text-muted-foreground mt-1 block font-mono text-[0.75rem]">{item.policy.join(", ")}</span>}
                </span>
              </>
            );
            return (
              <li key={item.key}>
                {field ? (
                  <label
                    className={cn(
                      "has-focus-visible:ring-ring/40 flex cursor-pointer items-start gap-3 rounded-lg border p-3 transition-colors has-focus-visible:ring-[3px] has-disabled:cursor-not-allowed has-disabled:opacity-55",
                      done ? "border-primary/30 bg-accent/50" : "bg-background",
                    )}
                  >
                    <input
                      type="checkbox"
                      className="sr-only"
                      checked={done}
                      disabled={!reachedCustomer}
                      onChange={(e) => update((o) => ({ ...o, [field]: e.target.checked }))}
                    />
                    {box}
                  </label>
                ) : (
                  <div className="flex items-start gap-3 rounded-lg border border-dashed p-3">{box}</div>
                )}
              </li>
            );
          })}
        </ul>
      )}
      {guide.length > 0 && (
        <div className="mt-4 border-t pt-3">
          <h4 className="text-muted-foreground mb-1.5 text-xs font-medium">Then, during the call</h4>
          <ol className="space-y-1">
            {guide.map((item) => (
              <li key={item.key} className="flex items-start gap-2.5 py-1 text-sm" title={item.policy.join(", ") || undefined}>
                {item.done ? (
                  <CheckCircle2 className="text-primary mt-0.5 size-4 shrink-0" aria-hidden />
                ) : (
                  <Circle className="text-muted-foreground/60 mt-0.5 size-4 shrink-0" aria-hidden />
                )}
                <span className="min-w-0 leading-snug">
                  <span className="font-medium">{scriptLabel(item.key)}</span>
                  {item.done && <span className="sr-only"> (done)</span>}
                  <span className="text-muted-foreground"> {item.text}</span>
                </span>
              </li>
            ))}
          </ol>
        </div>
      )}
    </CallStep>
  );
}

function Chip({
  pressed,
  onToggle,
  children,
  tone = "default",
}: {
  pressed: boolean;
  onToggle: () => void;
  children: React.ReactNode;
  tone?: "default" | "stop";
}) {
  return (
    <button
      type="button"
      aria-pressed={pressed}
      onClick={onToggle}
      className={cn(
        "focus-visible:ring-ring/40 inline-flex h-9 items-center gap-1.5 rounded-full border px-3.5 text-sm font-medium transition-colors outline-none focus-visible:ring-[3px] disabled:cursor-not-allowed disabled:opacity-50",
        !pressed && "bg-background hover:border-primary/40",
        pressed && tone === "default" && "border-primary bg-primary text-primary-foreground",
        pressed && tone === "stop" && "border-destructive bg-destructive text-destructive-foreground",
      )}
    >
      {pressed ? <CheckCircle2 className="size-4" aria-hidden /> : <Circle className="text-muted-foreground size-4" aria-hidden />}
      {children}
    </button>
  );
}

function Select<T extends string>({
  id,
  label,
  value,
  options,
  onChange,
}: {
  id: string;
  label: string;
  value: T | null;
  options: Record<T, string>;
  onChange: (v: T | null) => void;
}) {
  return (
    <div className="space-y-1.5">
      <Label htmlFor={id}>{label}</Label>
      <select
        id={id}
        value={value ?? ""}
        onChange={(e) => onChange((e.target.value || null) as T | null)}
        className="border-input bg-card focus-visible:border-ring focus-visible:ring-ring/30 h-9 w-full rounded-md border px-3 text-sm outline-none focus-visible:ring-[3px]"
      >
        <option value="">Not given</option>
        {(Object.keys(options) as T[]).map((k) => (
          <option key={k} value={k}>
            {options[k]}
          </option>
        ))}
      </select>
    </div>
  );
}

/** Numeric input that keeps the typed text (e.g. "12.") while reporting a parsed number or null. */
function NumberField({
  id,
  label,
  value,
  onChange,
  prefix = "$",
}: {
  id: string;
  label: string;
  value: number | null;
  onChange: (v: number | null) => void;
  prefix?: string;
}) {
  const [text, setText] = useState(value === null ? "" : String(value));
  useEffect(() => {
    setText((current) => {
      const parsed = current.trim() === "" ? null : Number(current);
      return parsed === value ? current : value === null ? "" : String(value);
    });
  }, [value]);
  return (
    <div className="space-y-1.5">
      <Label htmlFor={id}>{label}</Label>
      <div className="relative">
        <span className="text-muted-foreground pointer-events-none absolute top-1/2 left-3 -translate-y-1/2 text-sm" aria-hidden>
          {prefix}
        </span>
        <Input
          id={id}
          inputMode="decimal"
          autoComplete="off"
          className="pl-7 tabular-nums"
          value={text}
          onChange={(e) => {
            const raw = e.target.value.replace(/[^\d.]/g, "");
            setText(raw);
            const n = raw === "" ? null : Number(raw);
            onChange(n === null || Number.isFinite(n) ? n : null);
          }}
        />
      </div>
    </div>
  );
}

export interface CallDrafts {
  promise: { amount: number | null; date: string };
  callback: { date: string; time: string };
}

export const EMPTY_DRAFTS: CallDrafts = { promise: { amount: null, date: "" }, callback: { date: "", time: "" } };

type SetDrafts = (fn: (d: CallDrafts) => CallDrafts) => void;

function PromiseForm({ drafts, setDrafts, update, checks }: { drafts: CallDrafts; setDrafts: SetDrafts; update: Update; checks: Check[] }) {
  const { amount, date } = drafts.promise;
  function change(nextAmount: number | null, nextDate: string) {
    setDrafts((d) => ({ ...d, promise: { amount: nextAmount, date: nextDate } }));
    update((o) => ({ ...o, promise: nextAmount !== null && nextAmount > 0 && /^\d{4}-\d{2}-\d{2}$/.test(nextDate) ? { amount: nextAmount, date: nextDate } : null }));
  }
  return (
    <fieldset className="rounded-lg border p-4">
      <legend className="px-1 text-sm font-semibold">Promise to pay</legend>
      <div className="grid gap-3 sm:grid-cols-[1fr_1fr_auto] sm:items-end">
        <NumberField id="promise-amount" label="Amount" value={amount} onChange={(v) => change(v, date)} />
        <div className="space-y-1.5">
          <Label htmlFor="promise-date">Date</Label>
          <Input id="promise-date" type="date" value={date} onChange={(e) => change(amount, e.target.value)} />
        </div>
        {(amount !== null || date) && (
          <Button type="button" variant="ghost" size="sm" onClick={() => change(null, "")}>
            <X aria-hidden /> Clear
          </Button>
        )}
      </div>
      {amount !== null && !date && <p className="text-muted-foreground mt-2 text-xs">Add the date to check the promise.</p>}
      <InlineChecks checks={checks} prefix="promise" />
    </fieldset>
  );
}

function CallbackForm({ drafts, setDrafts, update, checks }: { drafts: CallDrafts; setDrafts: SetDrafts; update: Update; checks: Check[] }) {
  const { date, time } = drafts.callback;
  function change(d: string, t: string) {
    setDrafts((x) => ({ ...x, callback: { date: d, time: t } }));
    update((o) => ({ ...o, callback: d && t ? { date: d, time: t } : null }));
  }
  return (
    <fieldset className="rounded-lg border p-4">
      <legend className="px-1 text-sm font-semibold">Callback</legend>
      <div className="grid gap-3 sm:grid-cols-[1fr_1fr_auto] sm:items-end">
        <div className="space-y-1.5">
          <Label htmlFor="callback-date">Date</Label>
          <Input id="callback-date" type="date" value={date} onChange={(e) => change(e.target.value, time)} />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="callback-time">Their local time</Label>
          <Input id="callback-time" type="time" value={time} onChange={(e) => change(date, e.target.value)} />
        </div>
        {(date || time) && (
          <Button type="button" variant="ghost" size="sm" onClick={() => change("", "")}>
            <X aria-hidden /> Clear
          </Button>
        )}
      </div>
      <InlineChecks checks={checks} prefix="callback" />
    </fieldset>
  );
}

function ConversationStep({ session, outcomes, update, drafts, setDrafts }: { session: CallSession; outcomes: Outcomes; update: Update; drafts: CallDrafts; setDrafts: SetDrafts }) {
  const locked = !session.can_discuss_debt;
  return (
    <CallStep n={3} title="What the customer says" hint="Tick what you hear. The plan on the right updates as you go.">
      {locked && (
        <div className="bg-muted/60 mb-4 flex items-start gap-3 rounded-lg border border-dashed p-3 text-sm">
          <Lock className="text-muted-foreground mt-0.5 size-4 shrink-0" aria-hidden />
          <p>
            <strong>Locked until the customer is reached and their identity is verified.</strong>{" "}
            <span className="text-muted-foreground">Account details are never discussed before that.</span>
          </p>
        </div>
      )}
      <fieldset disabled={locked} className={cn("min-w-0 space-y-5 transition-opacity", locked && "pointer-events-none opacity-45 select-none")} aria-describedby={undefined}>
        <legend className="sr-only">Conversation outcomes</legend>
        <div className="flex flex-wrap gap-2">
          <Chip pressed={outcomes.hardship.stated} onToggle={() => update((o) => ({ ...o, hardship: { stated: !o.hardship.stated, reason: o.hardship.stated ? null : o.hardship.reason } }))}>
            Hardship
          </Chip>
          <Chip pressed={outcomes.cannot_afford} onToggle={() => update((o) => ({ ...o, cannot_afford: !o.cannot_afford }))}>
            Cannot afford
          </Chip>
          <Chip pressed={outcomes.dispute.raised} onToggle={() => update((o) => ({ ...o, dispute: { raised: !o.dispute.raised, type: o.dispute.raised ? null : o.dispute.type } }))}>
            Dispute
          </Chip>
          <Chip pressed={outcomes.complaint} onToggle={() => update((o) => ({ ...o, complaint: !o.complaint }))}>
            Complaint
          </Chip>
          <Chip pressed={outcomes.vulnerable_disclosed} onToggle={() => update((o) => ({ ...o, vulnerable_disclosed: !o.vulnerable_disclosed }))}>
            Vulnerability disclosed
          </Chip>
          <Chip
            tone="stop"
            pressed={outcomes.representative.stated}
            onToggle={() => update((o) => ({ ...o, representative: { stated: !o.representative.stated, kind: o.representative.stated ? null : o.representative.kind } }))}
          >
            Has a representative
          </Chip>
          <Chip tone="stop" pressed={outcomes.cease_request} onToggle={() => update((o) => ({ ...o, cease_request: !o.cease_request }))}>
            Asked us to stop contact
          </Chip>
        </div>

        {(outcomes.hardship.stated || outcomes.dispute.raised || outcomes.representative.stated) && (
          <div className="grid gap-3 sm:grid-cols-2">
            {outcomes.hardship.stated && (
              <Select
                id="hardship-reason"
                label="Hardship reason"
                value={outcomes.hardship.reason}
                options={HARDSHIP_REASON_LABEL}
                onChange={(v) => update((o) => ({ ...o, hardship: { stated: true, reason: v } }))}
              />
            )}
            {outcomes.dispute.raised && (
              <Select
                id="dispute-type"
                label="Dispute is about"
                value={outcomes.dispute.type}
                options={DISPUTE_TYPE_LABEL}
                onChange={(v) => update((o) => ({ ...o, dispute: { raised: true, type: v } }))}
              />
            )}
            {outcomes.representative.stated && (
              <Select
                id="representative-kind"
                label="Representative"
                value={outcomes.representative.kind}
                options={REPRESENTATIVE_LABEL}
                onChange={(v) => update((o) => ({ ...o, representative: { stated: true, kind: v } }))}
              />
            )}
          </div>
        )}

        <fieldset className="rounded-lg border p-4">
          <legend className="px-1 text-sm font-semibold">Income and expenses the customer states</legend>
          <div className="grid gap-3 sm:grid-cols-2">
            <NumberField
              id="income-monthly"
              label="Monthly income"
              value={outcomes.income.monthly_income}
              onChange={(v) => update((o) => ({ ...o, income: { ...o.income, monthly_income: v } }))}
            />
            <NumberField
              id="expenses-monthly"
              label="Monthly expenses"
              value={outcomes.income.monthly_expenses}
              onChange={(v) => update((o) => ({ ...o, income: { ...o.income, monthly_expenses: v } }))}
            />
          </div>
          <p className="text-muted-foreground mt-2 text-xs">Recorded as stated by the customer. Not verified.</p>
        </fieldset>

        <PromiseForm drafts={drafts} setDrafts={setDrafts} update={update} checks={session.checks} />
        <CallbackForm drafts={drafts} setDrafts={setDrafts} update={update} checks={session.checks} />
      </fieldset>
    </CallStep>
  );
}

export function GuidedCall({
  session,
  outcomes,
  update,
  disabled,
  notes,
  drafts,
  setDrafts,
}: {
  session: CallSession;
  outcomes: Outcomes;
  update: Update;
  disabled: boolean;
  notes: React.ReactNode;
  drafts: CallDrafts;
  setDrafts: SetDrafts;
}) {
  return (
    <fieldset disabled={disabled} className="min-w-0 space-y-4">
      <legend className="sr-only">Guided call</legend>
      {disabled && (
        <p className="text-destructive flex items-center gap-2 text-sm font-medium">
          <Ban className="size-4" aria-hidden /> This customer must not be contacted. The call steps are shown for reference only.
        </p>
      )}
      <div className={cn("space-y-4", disabled && "pointer-events-none opacity-45 select-none")} aria-hidden={disabled || undefined}>
        <ReachedStep outcomes={outcomes} update={update} />
        <ChecklistStep session={session} outcomes={outcomes} update={update} />
        <ConversationStep session={session} outcomes={outcomes} update={update} drafts={drafts} setDrafts={setDrafts} />
        {notes}
      </div>
    </fieldset>
  );
}
