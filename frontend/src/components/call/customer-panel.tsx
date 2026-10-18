"use client";

import { Ban, Clock, Languages } from "lucide-react";
import { PolicyLink } from "@/components/policy-link";
import { Badge } from "@/components/ui/badge";
import type { CallSession } from "@/lib/call-types";
import { formatMoney } from "@/lib/call-outcomes";

/** The backend sends a display string such as "Mon 28 Sep 07:00"; split off the time for emphasis. */
function localClock(value: string | null) {
  if (!value) return null;
  const match = value.match(/^(.*?)\s*(\d{1,2}:\d{2})$/);
  return match ? { day: match[1], time: match[2] } : { day: "", time: value };
}

const LANGUAGE: Record<string, string> = { EN: "English", FR: "Français" };

export function CustomerPanel({ session }: { session: CallSession }) {
  const c = session.customer;
  const clock = localClock(c.local_time_now);
  const lang = c.preferred_language.toUpperCase();
  const contact = session.plan.contact_window;
  const blocked = session.stage === "blocked";
  const stop = session.plan.steps.find((s) => s.status === "stop") ?? session.plan.steps[0];

  return (
    <div className="@container space-y-4">
      <section aria-label="Customer" className="bg-card rounded-xl border p-5 shadow-xs">
        <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-2">
          <div className="min-w-0">
            <h2 className="text-xl leading-tight font-semibold break-words">{c.name}</h2>
            <p className="text-muted-foreground mt-1 font-mono text-xs break-all">
              {c.customer_id} / {c.case_id}
            </p>
          </div>
          <Badge variant={lang === "FR" ? "review" : "outline"} className="text-[0.8rem]">
            <Languages aria-hidden /> {LANGUAGE[lang] ?? lang}
          </Badge>
        </div>

        <dl className="mt-5 grid grid-cols-2 gap-x-4 gap-y-4 @xl:grid-cols-5">
          <div>
            <dt className="text-muted-foreground text-xs">Product</dt>
            <dd className="mt-0.5 font-medium capitalize">{c.product.replace(/_/g, " ")}</dd>
          </div>
          <div>
            <dt className="text-muted-foreground text-xs">Days past due</dt>
            <dd className="mt-0.5 font-medium tabular-nums">{c.dpd}</dd>
          </div>
          <div>
            <dt className="text-muted-foreground text-xs">Overdue</dt>
            <dd className="mt-0.5 font-medium tabular-nums">{formatMoney(c.overdue_cad)}</dd>
          </div>
          <div className="col-span-2 @xl:col-span-2">
            <dt className="text-muted-foreground flex items-center gap-1 text-xs">
              <Clock className="size-3" aria-hidden /> Their local time
            </dt>
            <dd className="mt-0.5">
              {clock ? (
                <>
                  <span className="text-2xl font-semibold tabular-nums">{clock.time}</span>{" "}
                  <span className="text-muted-foreground text-sm">
                    {clock.day} {c.time_zone.replace("America/", "").replace(/_/g, " ")}
                  </span>
                </>
              ) : (
                <span className="text-muted-foreground text-sm">No call allowed</span>
              )}
              {c.call_time_note && clock && <span className="text-muted-foreground mt-1 block text-xs leading-snug">{c.call_time_note}</span>}
            </dd>
          </div>
        </dl>

        {lang === "FR" && <p className="text-review-foreground mt-3 text-sm">Preferred language is French. Offer to continue in French.</p>}

        {contact && !blocked && (
          <p className="text-muted-foreground mt-4 border-t pt-3 text-sm leading-snug">
            {contact.available ? (
              <>
                Next permitted contact: <strong className="text-foreground">{contact.day}</strong>, {contact.from_local}–{contact.until_local}.{" "}
                {contact.attempts_last_7d}/{contact.cap_7d ?? 3} attempts used in 7 days.
              </>
            ) : (
              <>No permitted contact slot in the next 21 days.</>
            )}
          </p>
        )}
      </section>

      {blocked && (
        <section
          aria-label="Contact restriction"
          role="alert"
          className="border-destructive bg-destructive text-destructive-foreground rounded-xl border-2 p-5 shadow-sm"
        >
          <p className="flex items-center gap-2 text-2xl font-semibold tracking-tight">
            <Ban className="size-7" aria-hidden /> Do not contact
          </p>
          {stop && (
            <>
              <p className="mt-3 font-medium">{stop.title}</p>
              <p className="mt-1 text-sm leading-relaxed opacity-90">{stop.detail}</p>
              {stop.policy.length > 0 && (
                <p className="mt-3 flex flex-wrap gap-1.5">
                  {stop.policy.map((p) => (
                    <PolicyLink key={p} text={p} variant="onDark" />
                  ))}
                </p>
              )}
            </>
          )}
          <p className="mt-4 border-t border-white/25 pt-3 text-sm">Call controls are switched off for this customer.</p>
        </section>
      )}
    </div>
  );
}
