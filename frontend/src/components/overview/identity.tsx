"use client";

import Link from "next/link";
import { useInView } from "@/components/motion/reveal";
import { cn, formatCount } from "@/lib/utils";
import styles from "./overview.module.css";

interface IdentityCounts {
  matched: number;
  review: number;
  unmatched: number;
}

/** How source records were joined, plus the build's failed quality checks. */
export function Identity({
  identity,
  qualityIssues,
  qualityHref,
}: {
  identity: IdentityCounts;
  qualityIssues: number;
  qualityHref?: string;
}) {
  const [ref, shown] = useInView<HTMLDivElement>();
  const total = identity.matched + identity.review + identity.unmatched;
  const segments = [
    { key: "matched", label: "Matched", value: identity.matched, color: "bg-primary" },
    { key: "review", label: "Needs a person to check", value: identity.review, color: "bg-review" },
    { key: "unmatched", label: "Not matched", value: identity.unmatched, color: "bg-seaglass-deep" },
  ];
  return (
    <section aria-labelledby="identity-heading" className="grid gap-6 lg:grid-cols-[17rem_1fr] lg:gap-16">
      <div>
        <h2 id="identity-heading" className="text-[1.75rem] leading-tight font-normal tracking-[-0.015em]">
          Identity matching
        </h2>
        <p className="text-muted-foreground mt-3 leading-relaxed">
          How records from six bank systems were linked to one customer. Uncertain matches are never accepted
          automatically.
        </p>
      </div>

      <div ref={ref} data-shown={shown}>
        {total > 0 ? (
          <div className="bg-seaglass/60 flex h-3 w-full overflow-hidden rounded-full" aria-hidden>
            <div className={cn(styles.bar, "flex h-full w-full")}>
              {segments.map((s) =>
                s.value > 0 ? <div key={s.key} className={s.color} style={{ width: `${(s.value / total) * 100}%` }} /> : null,
              )}
            </div>
          </div>
        ) : (
          <p className="text-muted-foreground">No identity results reported.</p>
        )}
        <dl className="mt-6 grid gap-6 sm:grid-cols-3">
          {segments.map((s) => (
            <div key={s.key}>
              <dt className="text-muted-foreground flex items-center gap-2 text-[0.9375rem]">
                <span className={`${s.color} size-2.5 rounded-full`} aria-hidden />
                {s.label}
              </dt>
              <dd className="mt-1.5 text-[1.75rem] leading-none tracking-[-0.02em] tabular-nums">
                {formatCount(s.value)}
                {total > 0 && (
                  <span className="text-muted-foreground ml-2 text-sm tracking-normal">{((s.value / total) * 100).toFixed(1)}%</span>
                )}
              </dd>
            </div>
          ))}
        </dl>
        <p className="text-muted-foreground border-line-soft mt-8 border-t pt-5 leading-relaxed">
          The latest build also counted {formatCount(qualityIssues)} failed data-quality checks.{" "}
          {qualityHref && (
            <Link href={qualityHref} className="text-primary rounded font-medium underline-offset-4 outline-none hover:underline focus-visible:ring-[3px] focus-visible:ring-ring/35">
              See what failed
            </Link>
          )}
        </p>
      </div>
    </section>
  );
}
