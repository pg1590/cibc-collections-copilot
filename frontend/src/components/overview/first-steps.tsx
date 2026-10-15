"use client";

import { useInView } from "@/components/motion/reveal";
import { cn, formatCount } from "@/lib/utils";
import styles from "./overview.module.css";

export interface PlanSummary {
  plans: number;
  next_step_counts: Record<string, number>;
}

const NEXT_STEP_LABEL: Record<string, string> = {
  payment_ask: "Ask for payment, timed to payday",
  promise: "Remind about an open promise",
  hardship: "Offer a hardship programme first",
  restriction: "Don't contact (restriction)",
  representative: "Contact the representative only",
  vulnerability: "Vulnerable-customer approach first",
  dispute: "Pause the disputed amount",
  complaint: "Handle the open complaint",
  placement: "Coordinate with agency or legal",
};

/** How tomorrow's calls start: the first step of every open case's plan. */
export function FirstSteps({ plans }: { plans: PlanSummary }) {
  const [ref, shown] = useInView<HTMLUListElement>();
  const rows = Object.entries(plans.next_step_counts).sort((a, b) => b[1] - a[1]);
  const max = Math.max(...rows.map(([, n]) => n), 1);
  return (
    <section aria-labelledby="steps-heading">
      <h2 id="steps-heading" className="text-[1.75rem] leading-tight font-normal tracking-[-0.015em]">
        Today&apos;s first step, across every open case
      </h2>
      <p className="text-muted-foreground mt-3 max-w-2xl leading-relaxed">
        From the nightly plan for {formatCount(plans.plans)} customers with an open case. Each bar counts the step an
        agent would take first.
      </p>
      <ul ref={ref} data-shown={shown} className="mt-7 space-y-4" aria-label="First step by number of customers">
        {rows.map(([key, n], i) => {
          const label = NEXT_STEP_LABEL[key] ?? key;
          const share = (n / plans.plans) * 100;
          return (
            <li key={key} className="grid items-center gap-x-6 gap-y-1.5 md:grid-cols-[17rem_1fr]">
              <span className="text-[0.9375rem]">{label}</span>
              <span className="flex items-center gap-3">
                <span className="bg-muted h-2.5 flex-1 overflow-hidden rounded-full" aria-hidden>
                  <span
                    className={cn(styles.bar, "bg-primary block h-full rounded-full")}
                    style={{ width: `${Math.max((n / max) * 100, 1)}%`, "--i": i } as React.CSSProperties}
                  />
                </span>
                <span className="text-muted-foreground w-28 shrink-0 text-right text-sm tabular-nums">
                  {formatCount(n)} <span className="text-muted-foreground/80">({share.toFixed(0)}%)</span>
                </span>
              </span>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
