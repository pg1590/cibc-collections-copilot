"use client";

import Link from "next/link";
import { AlertTriangle, RotateCw } from "lucide-react";
import { FirstSteps, type PlanSummary } from "@/components/overview/first-steps";
import { Identity } from "@/components/overview/identity";
import styles from "@/components/overview/overview.module.css";
import { Problems } from "@/components/overview/problems";
import { money, Stakes, type ValueItem } from "@/components/overview/stakes";
import { ErrorState, LoadingState } from "@/components/states";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Skeleton } from "@/components/ui/skeleton";
import { canSee, useAuth } from "@/lib/auth";
import type { PortfolioChecks } from "@/lib/plan-types";
import { useApi } from "@/lib/use-api";
import type { Health, Overview } from "@/lib/types";
import { formatCad, formatCount } from "@/lib/utils";

interface PortfolioValue {
  items: ValueItem[];
  plans: PlanSummary | null;
}

function greeting(now = new Date()) {
  const hour = now.getHours();
  return hour < 12 ? "Good morning" : hour < 18 ? "Good afternoon" : "Good evening";
}

function asOf(snapshot: string | null | undefined) {
  if (!snapshot) return null;
  const date = new Date(`${snapshot}T12:00:00`);
  return Number.isNaN(date.getTime())
    ? snapshot
    : date.toLocaleDateString("en-GB", { weekday: "long", day: "numeric", month: "long", year: "numeric" });
}

export default function OverviewPage() {
  const { session } = useAuth();
  const role = session?.user.role;
  const health = useApi<Health>("/health");
  const overview = useApi<Overview>("/overview");
  const showChecks = role === "analyst" || role === "supervisor";
  const checks = useApi<PortfolioChecks>(showChecks ? "/overview/checks" : null);
  const value = useApi<PortfolioValue>(showChecks ? "/overview/value" : null);

  const refresh = () => {
    health.reload();
    overview.reload();
    if (showChecks) {
      checks.reload();
      value.reload();
    }
  };

  const data = overview.data;
  const yours = role === "agent";
  const date = asOf(health.data?.snapshot_date);
  const headline = data
    ? [
        { label: yours ? "Your open cases" : "Open cases", value: formatCount(data.open_cases), full: undefined },
        { label: yours ? "Overdue on your cases" : "Overdue", value: money.format(data.overdue_cad), full: formatCad(data.overdue_cad) },
        { label: yours ? "Your customers" : "Customers", value: formatCount(data.customers), full: undefined },
      ]
    : [];

  return (
    <div className="space-y-16 sm:space-y-20">
      {/* Chapter 0: greeting and the three numbers that matter most. */}
      <div className="hero-panel overflow-hidden rounded-[1.75rem] px-6 py-10 text-white sm:px-10 sm:py-12">
        <div className={styles.heroText}>
          <div className="flex items-start justify-between gap-4">
            <p className="text-lg text-white/80">{greeting()}</p>
            <button
              type="button"
              onClick={refresh}
              className="inline-flex items-center gap-1.5 rounded-full bg-white/10 px-3 py-1.5 text-sm text-white/90 ring-1 ring-white/15 transition-colors outline-none hover:bg-white/18 hover:text-white focus-visible:ring-[3px] focus-visible:ring-white/50"
            >
              <RotateCw className="size-4" aria-hidden /> Refresh
            </button>
          </div>
          <h1 className="mt-2 text-[2.5rem] leading-[1.08] font-normal tracking-[-0.025em] sm:text-[3.25rem]">
            Here&apos;s where things stand.
          </h1>
          {date && (
            <p className="mt-4 max-w-xl text-[1.0625rem] leading-relaxed text-white/80">
              Counts from the data build as of {date}. Nothing on this page is estimated unless it says so.
            </p>
          )}
        </div>

        <div className={styles.heroNumbers}>
          {overview.loading ? (
            <div role="status" className="mt-10 grid gap-8 sm:grid-cols-3">
              <span className="sr-only">Loading overview…</span>
              {[0, 1, 2].map((i) => (
                <Skeleton key={i} className="h-20 rounded-2xl bg-white/15" />
              ))}
            </div>
          ) : overview.error ? (
            <div className="mt-10">
              {health.data && !health.data.dataset_ready ? (
                <Alert variant="review">
                  <AlertTriangle aria-hidden />
                  <AlertTitle>No counts yet</AlertTitle>
                  <AlertDescription>
                    <p>The data build hasn&apos;t run, so there is nothing to count yet. Backend says: {overview.error}</p>
                  </AlertDescription>
                </Alert>
              ) : (
                <ErrorState message={overview.error} onRetry={overview.reload} />
              )}
            </div>
          ) : (
            data && (
              <>
                <dl className="mt-10 grid gap-8 sm:grid-cols-3 sm:gap-0 sm:divide-x sm:divide-white/15">
                  {headline.map((h) => (
                    <div key={h.label} className="flex flex-col-reverse sm:px-8 sm:first:pl-0">
                      <dt className="mt-3 text-[1.0625rem] text-white/80">{h.label}</dt>
                      <dd className="text-[3rem] leading-none tracking-[-0.03em] tabular-nums sm:text-[3.5rem] lg:text-[4.25rem]" title={h.full}>
                        {h.value}
                      </dd>
                    </div>
                  ))}
                </dl>
                {data.pending_reviews > 0 && canSee(role, "reviews") && (
                  <Link
                    href="/reviews"
                    className="bg-review-soft text-review-foreground mt-8 inline-flex items-center gap-2.5 rounded-full px-4 py-2 text-[0.9375rem] font-medium shadow-[0_8px_24px_-12px_rgb(0_0_0/0.35)] outline-none hover:bg-white focus-visible:ring-[3px] focus-visible:ring-white/50"
                  >
                    <span className="bg-review size-2 rounded-full" aria-hidden />
                    {yours
                      ? `${formatCount(data.pending_reviews)} of your drafts ${data.pending_reviews === 1 ? "is" : "are"} waiting for a supervisor`
                      : `${formatCount(data.pending_reviews)} ${data.pending_reviews === 1 ? "draft is" : "drafts are"} waiting for your review`}
                  </Link>
                )}
              </>
            )
          )}
        </div>
      </div>

      {/* Chapter 1: what needs attention (analysts and supervisors). */}
      {showChecks &&
        (checks.loading ? (
          <LoadingState label="Running portfolio checks" rows={3} />
        ) : checks.error ? (
          <ErrorState message={checks.error} onRetry={checks.reload} />
        ) : (
          checks.data && <Problems checks={checks.data.items} />
        ))}

      {/* Chapter 2: the money behind it, told step by step. */}
      {showChecks && value.data && value.data.items.length > 0 && <Stakes items={value.data.items} />}

      {/* Chapter 3: how tomorrow's calls begin. */}
      {showChecks && value.data?.plans && <FirstSteps plans={value.data.plans} />}

      {/* Chapter 4: how the data was joined. */}
      {data && (
        <Identity
          identity={data.identity}
          qualityIssues={data.quality_issues}
          qualityHref={canSee(role, "quality") ? "/quality" : undefined}
        />
      )}
    </div>
  );
}
