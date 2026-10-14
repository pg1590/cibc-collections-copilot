"use client";

import Link from "next/link";
import { AlertTriangle, ArrowRight, CheckCircle2, ChevronDown, CircleDashed, RotateCw } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { ErrorState, LoadingState } from "@/components/states";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import type { PortfolioCheck, PortfolioChecks } from "@/lib/plan-types";
import { canSee, useAuth } from "@/lib/auth";
import { useApi } from "@/lib/use-api";
import type { Health, Overview } from "@/lib/types";
import { formatCad, formatCount } from "@/lib/utils";

function Stat({ label, value, hint, href, tone }: { label: string; value: string; hint: string; href?: string; tone?: "review" }) {
  const body = (
    <Card className="h-full gap-2 py-5 transition-colors group-hover:border-primary/40">
      <CardContent className="space-y-1">
        <p className="text-muted-foreground text-sm">{label}</p>
        <p className={tone === "review" ? "text-review-foreground text-3xl font-semibold tabular-nums" : "text-3xl font-semibold tabular-nums"}>
          {value}
        </p>
        <p className="text-muted-foreground text-xs">{hint}</p>
      </CardContent>
    </Card>
  );
  return href ? (
    <Link href={href} className="group rounded-xl outline-none focus-visible:ring-[3px] focus-visible:ring-ring/40">
      {body}
    </Link>
  ) : (
    body
  );
}

function CheckCard({ check }: { check: PortfolioCheck }) {
  return (
    <Card className={check.severity === "high" ? "border-l-review gap-3 border-l-4 py-5" : "gap-3 py-5"}>
      <CardContent className="space-y-2">
        <p className="text-muted-foreground text-sm leading-snug">{check.title}</p>
        <p className="text-3xl font-semibold tabular-nums">
          {formatCount(check.value)} <span className="text-muted-foreground text-sm font-normal">{check.unit}</span>
        </p>
        <p className="text-sm leading-snug">{check.action}</p>
        <Collapsible>
          <CollapsibleTrigger className="text-muted-foreground hover:text-foreground group flex items-center gap-1 text-xs underline-offset-4 hover:underline">
            <ChevronDown className="size-3.5 transition-transform group-data-[state=open]:rotate-180" aria-hidden /> Definition and SQL
          </CollapsibleTrigger>
          <CollapsibleContent className="mt-2 space-y-2">
            <p className="text-xs leading-relaxed">{check.definition}</p>
            <Badge variant="teal" className="font-mono whitespace-normal">
              {check.policy}
            </Badge>
            <pre className="bg-muted/60 overflow-x-auto rounded-md p-2 font-mono text-[0.7rem] leading-relaxed whitespace-pre-wrap">{check.sql}</pre>
          </CollapsibleContent>
        </Collapsible>
      </CardContent>
    </Card>
  );
}

export default function OverviewPage() {
  const { session } = useAuth();
  const role = session?.user.role;
  const health = useApi<Health>("/health");
  const overview = useApi<Overview>("/overview");
  const showChecks = role === "analyst" || role === "supervisor";
  const checks = useApi<PortfolioChecks>(showChecks ? "/overview/checks" : null);

  const identity = overview.data?.identity;
  const identityTotal = identity ? identity.matched + identity.review + identity.unmatched : 0;
  const segments = identity
    ? [
        { key: "matched", label: "Matched", value: identity.matched, color: "bg-primary" },
        { key: "review", label: "Needs review", value: identity.review, color: "bg-review" },
        { key: "unmatched", label: "Unmatched", value: identity.unmatched, color: "bg-muted-foreground/40" },
      ]
    : [];

  return (
    <>
      <PageHeader
        title="Overview"
        description="Counts produced by the data pipeline for the current snapshot. Nothing on this page is estimated."
        actions={
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              health.reload();
              overview.reload();
              if (showChecks) checks.reload();
            }}
          >
            <RotateCw aria-hidden /> Refresh
          </Button>
        }
      />

      <section aria-labelledby="pipeline-heading" className="mb-8">
        <h2 id="pipeline-heading" className="sr-only">
          Pipeline state
        </h2>
        {health.loading ? (
          <LoadingState label="Checking pipeline" rows={1} />
        ) : health.error ? (
          <ErrorState title="Backend not reachable" message={health.error} onRetry={health.reload} />
        ) : health.data && (
          <Card className="py-4">
            <CardContent className="flex flex-wrap items-center gap-x-8 gap-y-3 text-sm">
              <span className="flex items-center gap-2">
                {health.data.dataset_ready ? (
                  <CheckCircle2 className="text-success size-4" aria-hidden />
                ) : (
                  <CircleDashed className="text-review size-4" aria-hidden />
                )}
                <span className="font-medium">{health.data.dataset_ready ? "Dataset loaded" : "Dataset not loaded yet"}</span>
              </span>
              <span>
                <span className="text-muted-foreground">Snapshot </span>
                <span className="font-medium">{health.data.snapshot_date ?? "—"}</span>
              </span>
              <span>
                <span className="text-muted-foreground">Runtime </span>
                <span className="font-medium">{health.data.runtime_mode}</span>
              </span>
              <span>
                <span className="text-muted-foreground">API status </span>
                <span className="font-medium">{health.data.status}</span>
              </span>
            </CardContent>
          </Card>
        )}
      </section>

      {overview.loading ? (
        <LoadingState label="Loading overview" rows={4} />
      ) : overview.error ? (
        health.data && !health.data.dataset_ready ? (
          <Alert variant="review">
            <AlertTriangle aria-hidden />
            <AlertTitle>No counts yet</AlertTitle>
            <AlertDescription>
              <p>The pipeline has not built the dataset, so there is nothing to count. Backend says: {overview.error}</p>
            </AlertDescription>
          </Alert>
        ) : (
          <ErrorState message={overview.error} onRetry={overview.reload} />
        )
      ) : (
        overview.data && (
          <div className="space-y-8">
            <section aria-label="Key counts" className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              <Stat label="Customers" value={formatCount(overview.data.customers)} hint="Golden customer records" href="/customers" />
              <Stat label="Open cases" value={formatCount(overview.data.open_cases)} hint="Collections cases still open" />
              <Stat label="Overdue balance" value={formatCad(overview.data.overdue_cad)} hint="Total past-due amount, CAD" />
              <Stat
                label="Pending reviews"
                value={formatCount(overview.data.pending_reviews)}
                hint="Agent drafts waiting for a supervisor"
                href={canSee(role, "reviews") ? "/reviews" : undefined}
                tone={overview.data.pending_reviews > 0 ? "review" : undefined}
              />
              <Stat
                label="Data quality issues"
                value={formatCount(overview.data.quality_issues)}
                hint="Failed checks in the latest build"
                href={canSee(role, "quality") ? "/quality" : undefined}
              />
            </section>

            {showChecks && (
              <section aria-labelledby="checks-heading" className="space-y-3">
                <div>
                  <h2 id="checks-heading" className="text-lg font-semibold">
                    Problems across all customers
                  </h2>
                  <p className="text-muted-foreground text-sm">
                    Policy checks over the whole portfolio at the snapshot. Each number is one SQL query you can open and rerun.
                  </p>
                </div>
                {checks.loading ? (
                  <LoadingState label="Running portfolio checks" rows={2} />
                ) : checks.error ? (
                  <ErrorState message={checks.error} onRetry={checks.reload} />
                ) : (
                  checks.data && (
                    <div className="grid items-start gap-4 sm:grid-cols-2 lg:grid-cols-3">
                      {checks.data.items.map((c) => (
                        <CheckCard key={c.id} check={c} />
                      ))}
                    </div>
                  )
                )}
              </section>
            )}

            <Card>
              <CardHeader>
                <CardTitle>Identity matching</CardTitle>
                <CardDescription>
                  How source-system customer keys were linked to one golden customer ID. “Needs review” means the match is
                  uncertain and should be checked by a person.
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                {identityTotal > 0 ? (
                  <div className="bg-muted flex h-3 w-full overflow-hidden rounded-full" aria-hidden>
                    {segments.map((s) =>
                      s.value > 0 ? <div key={s.key} className={s.color} style={{ width: `${(s.value / identityTotal) * 100}%` }} /> : null,
                    )}
                  </div>
                ) : (
                  <p className="text-muted-foreground text-sm">No identity results reported.</p>
                )}
                <dl className="grid gap-4 sm:grid-cols-3">
                  {segments.map((s) => (
                    <div key={s.key} className="flex items-start gap-2.5">
                      <span className={`${s.color} mt-1.5 size-2.5 shrink-0 rounded-full`} aria-hidden />
                      <div>
                        <dt className="text-muted-foreground text-sm">{s.label}</dt>
                        <dd className="text-xl font-semibold tabular-nums">
                          {formatCount(s.value)}
                          {identityTotal > 0 && (
                            <span className="text-muted-foreground ml-2 text-sm font-normal">
                              {((s.value / identityTotal) * 100).toFixed(1)}%
                            </span>
                          )}
                        </dd>
                      </div>
                    </div>
                  ))}
                </dl>
              </CardContent>
            </Card>

            <nav aria-label="Next steps" className="flex flex-wrap gap-2">
              {canSee(role, "ask") && (
                <Button asChild variant="outline">
                  <Link href="/ask">
                    Ask a question <ArrowRight aria-hidden />
                  </Link>
                </Button>
              )}
              {canSee(role, "briefs") && (
                <Button asChild variant="outline">
                  <Link href="/briefs">
                    Prepare an agent brief <ArrowRight aria-hidden />
                  </Link>
                </Button>
              )}
              {overview.data.pending_reviews > 0 && canSee(role, "reviews") && (
                <Badge variant="review" className="self-center">
                  {formatCount(overview.data.pending_reviews)} awaiting review
                </Badge>
              )}
            </nav>
          </div>
        )
      )}
    </>
  );
}
