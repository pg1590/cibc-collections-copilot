"use client";

import { useMemo, useState } from "react";
import {
  AlertTriangle,
  Ban,
  CalendarClock,
  CalendarX2,
  FileText,
  FolderOpen,
  HandCoins,
  Handshake,
  Mail,
  MessageSquare,
  Phone,
  PhoneIncoming,
  Smartphone,
  type LucideIcon,
} from "lucide-react";
import { ErrorState, EmptyState, LoadingState } from "@/components/states";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { useApi } from "@/lib/use-api";
import { cn, formatCad } from "@/lib/utils";

export interface TimelineEvent {
  ts: string;
  kind: "contact" | "promise" | "note" | "offer" | "case";
  case_id: string | null;
  channel: string | null;
  direction: string | null;
  code: string | null;
  title: string | null;
  amount: number | null;
  rpc: boolean | null;
  outside_rules: boolean;
  ref: string;
  detail: string | null;
}

interface Timeline {
  events: TimelineEvent[];
  counts: Record<string, number>;
  outside_rules: number;
  note: string;
}

interface CalendarDay {
  date: string;
  day: string;
  weekday: string;
  status: "open" | "cap" | "holiday" | "closed" | "blocked";
  from_local?: string;
  until_local?: string;
  reason: string | null;
}

interface ContactCalendar {
  time_zone: string;
  cap_7d: number;
  attempts_last_7d: number;
  days: CalendarDay[];
  note: string;
}

const FILTERS = [
  { key: "all", label: "All" },
  { key: "contact", label: "Contacts" },
  { key: "promise", label: "Promises" },
  { key: "note", label: "Notes" },
  { key: "offer", label: "Hardship offers" },
] as const;

function icon(e: TimelineEvent): LucideIcon {
  if (e.kind === "promise") return Handshake;
  if (e.kind === "note") return FileText;
  if (e.kind === "offer") return HandCoins;
  if (e.kind === "case") return FolderOpen;
  if (e.direction === "inbound") return PhoneIncoming;
  if (e.channel === "sms") return Smartphone;
  if (e.channel === "email") return Mail;
  if (e.channel === "call") return Phone;
  return MessageSquare;
}

const PROMISE_TONE: Record<string, "success" | "review" | "destructive" | "outline"> = {
  kept: "success",
  partially_kept: "review",
  broken: "destructive",
  open: "outline",
  cancelled: "outline",
};

function when(ts: string) {
  const d = new Date(ts.replace(" ", "T") + (ts.endsWith("Z") ? "" : "Z"));
  if (Number.isNaN(d.getTime())) return ts;
  return d.toLocaleString("en-CA", { dateStyle: "medium", timeStyle: "short", timeZone: "UTC" }) + " UTC";
}

export function CustomerTimeline({ customerId }: { customerId: string }) {
  const timeline = useApi<Timeline>(`/customers/${encodeURIComponent(customerId)}/timeline`);
  const [filter, setFilter] = useState<(typeof FILTERS)[number]["key"]>("all");
  const events = useMemo(
    () => (timeline.data?.events ?? []).filter((e) => filter === "all" || e.kind === filter),
    [timeline.data, filter],
  );

  return (
    <Card>
      <CardHeader>
        <CardTitle>History across systems</CardTitle>
        <CardDescription>
          Contacts, promises, notes, hardship offers and cases from every source system, newest first (last 12 months).
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {timeline.loading ? (
          <LoadingState label="Loading history" rows={4} />
        ) : timeline.error ? (
          <ErrorState message={timeline.error} onRetry={timeline.reload} />
        ) : (
          timeline.data && (
            <>
              <div className="flex flex-wrap items-center gap-2" role="group" aria-label="Filter history">
                {FILTERS.map((f) => {
                  const count = f.key === "all" ? timeline.data!.events.length : (timeline.data!.counts[f.key] ?? 0);
                  return (
                    <button
                      key={f.key}
                      type="button"
                      onClick={() => setFilter(f.key)}
                      aria-pressed={filter === f.key}
                      className={cn(
                        "rounded-full border px-3 py-1 text-sm transition-colors outline-none focus-visible:ring-[3px] focus-visible:ring-ring/40",
                        filter === f.key ? "bg-primary text-primary-foreground border-primary" : "bg-card hover:border-primary/40",
                      )}
                    >
                      {f.label} <span className="tabular-nums opacity-75">{count}</span>
                    </button>
                  );
                })}
                {timeline.data.outside_rules > 0 && (
                  <Badge variant="destructive" className="ml-auto">
                    <AlertTriangle aria-hidden /> {timeline.data.outside_rules} contact{timeline.data.outside_rules === 1 ? "" : "s"} outside permitted hours or on a holiday
                  </Badge>
                )}
              </div>
              {events.length ? (
                <ol className="relative space-y-3 border-l pl-5">
                  {events.map((e) => {
                    const Icon = icon(e);
                    return (
                      <li key={`${e.kind}-${e.ref}-${e.ts}`} className="relative">
                        <span
                          className={cn(
                            "bg-card absolute -left-[1.95rem] top-0.5 flex size-6 items-center justify-center rounded-full border",
                            e.outside_rules && "border-destructive text-destructive",
                          )}
                          aria-hidden
                        >
                          <Icon className="size-3.5" />
                        </span>
                        <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
                          <span className="text-sm font-medium">{e.title ?? e.kind}</span>
                          {e.kind === "promise" && e.code && <Badge variant={PROMISE_TONE[e.code] ?? "outline"}>{e.code.replace(/_/g, " ")}</Badge>}
                          {e.kind === "contact" && e.channel && (
                            <Badge variant="outline" className="capitalize">
                              {e.direction === "inbound" ? "inbound " : ""}
                              {e.channel}
                            </Badge>
                          )}
                          {e.rpc && <Badge variant="teal">Right party</Badge>}
                          {e.outside_rules && <Badge variant="destructive">Outside rules</Badge>}
                          {e.amount !== null && e.amount !== undefined && <span className="text-sm tabular-nums">{formatCad(e.amount)}</span>}
                          <span className="text-muted-foreground ml-auto text-xs whitespace-nowrap">{when(e.ts)}</span>
                        </div>
                        {e.detail && <p className="text-muted-foreground mt-0.5 line-clamp-3 text-sm">{e.detail}</p>}
                        <p className="text-muted-foreground font-mono text-[0.75rem]">
                          {e.ref}
                          {e.case_id && e.case_id !== e.ref ? ` · ${e.case_id}` : ""}
                        </p>
                      </li>
                    );
                  })}
                </ol>
              ) : (
                <EmptyState title="Nothing in this view" description="No events of this type in the last 12 months." />
              )}
            </>
          )
        )}
      </CardContent>
    </Card>
  );
}

const DAY_STYLE: Record<CalendarDay["status"], { tone: string; icon: LucideIcon | null; label: string }> = {
  open: { tone: "border-primary/30 bg-accent/60", icon: null, label: "Open" },
  cap: { tone: "border-review/40 bg-review-soft/60", icon: CalendarClock, label: "Cap reached" },
  holiday: { tone: "border-review/40 bg-review-soft/60", icon: CalendarX2, label: "Holiday" },
  closed: { tone: "bg-muted/60", icon: CalendarX2, label: "No contact" },
  blocked: { tone: "border-destructive/40 bg-destructive/5", icon: Ban, label: "Blocked" },
};

export function ContactCalendar({ customerId }: { customerId: string }) {
  const calendar = useApi<ContactCalendar>(`/customers/${encodeURIComponent(customerId)}/calendar`);
  return (
    <Card>
      <CardHeader>
        <CardTitle>When contact is allowed</CardTitle>
        <CardDescription>
          Next 14 days in the customer&apos;s own time zone, from the same rules as the brief: local hours, Sundays, statutory holidays, the 7-day
          attempt cap and recorded restrictions.
        </CardDescription>
      </CardHeader>
      <CardContent>
        {calendar.loading ? (
          <LoadingState label="Loading calendar" rows={2} />
        ) : calendar.error ? (
          calendar.error.includes("no open case") ? (
            <EmptyState title="No open case" description="Contact planning applies to customers with an open collections case." />
          ) : (
            <ErrorState message={calendar.error} onRetry={calendar.reload} />
          )
        ) : (
          calendar.data && (
            <div className="space-y-3">
              <p className="text-muted-foreground text-xs">
                {calendar.data.time_zone.replace("America/", "")} · {calendar.data.attempts_last_7d} of {calendar.data.cap_7d} attempts used in the last 7
                days
              </p>
              <ol className="grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-7" aria-label="Contact calendar">
                {calendar.data.days.map((d) => {
                  const style = DAY_STYLE[d.status];
                  const Icon = style.icon;
                  return (
                    <li key={d.date} className={cn("rounded-lg border p-2.5", style.tone)} title={d.reason ?? undefined}>
                      <p className="text-xs font-medium">{d.day}</p>
                      {d.status === "open" ? (
                        <p className="mt-1 text-sm font-semibold tabular-nums">
                          {d.from_local}–{d.until_local}
                        </p>
                      ) : (
                        <p className="mt-1 flex items-center gap-1 text-sm font-semibold">
                          {Icon && <Icon className="size-3.5" aria-hidden />} {style.label}
                        </p>
                      )}
                      {d.reason && <p className="text-muted-foreground mt-0.5 line-clamp-2 text-[0.75rem] leading-snug">{d.reason}</p>}
                    </li>
                  );
                })}
              </ol>
              <p className="text-muted-foreground text-xs">{calendar.data.note}</p>
            </div>
          )
        )}
      </CardContent>
    </Card>
  );
}
