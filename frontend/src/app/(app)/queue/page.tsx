"use client";

import Link from "next/link";
import { useState } from "react";
import { ArrowRight, PhoneCall, RotateCw } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { RoleGate } from "@/components/role-gate";
import { EmptyState, ErrorState, LoadingState } from "@/components/states";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useAuth } from "@/lib/auth";
import type { QueueItem, QueueResponse, QueueTier } from "@/lib/plan-types";
import { useApi } from "@/lib/use-api";
import { cn, formatCad, formatCount } from "@/lib/utils";

const TIER_BADGE: Record<QueueTier, "destructive" | "review" | "default" | "outline" | "secondary"> = {
  stop_now: "destructive",
  promise_due: "default",
  hardship_no_plan: "review",
  near_write_off: "review",
  promise_overdue: "secondary",
  standard: "outline",
  on_hold: "secondary",
};

const FLAG_LABEL: Record<string, string> = {
  representative: "Representative",
  dispute: "Open dispute",
  vulnerable_safeguard: "Vulnerable: safeguard",
  french: "French",
};

function NextContact({ item }: { item: QueueItem }) {
  const w = item.next_contact;
  if (!w) return <span className="text-muted-foreground">No contact</span>;
  if (!w.available) return <span className="text-review-foreground">No slot in 21 days</span>;
  return (
    <span className="whitespace-nowrap">
      {w.day}, {w.from_local}–{w.until_local}
      <span className="text-muted-foreground block text-xs">
        {w.time_zone.replace("America/", "")} · {w.attempts_last_7d}/3 used
      </span>
    </span>
  );
}

function QueueWorkspace() {
  const { session } = useAuth();
  const isAgent = session?.user.role === "agent";
  const [agent, setAgent] = useState<string>("");
  const [tier, setTier] = useState<QueueTier | "all">("all");
  const queue = useApi<QueueResponse>(`/queue${agent ? `?agent=${encodeURIComponent(agent)}` : ""}`);
  const data = queue.data;
  const items = data ? data.items.filter((i) => tier === "all" || i.tier === tier) : [];

  return (
    <>
      <div className="mb-6 flex flex-wrap items-end gap-3">
        {!isAgent && data?.agents && (
          <div className="space-y-1.5">
            <Label htmlFor="queue-agent">Agent</Label>
            <select
              id="queue-agent"
              value={agent || data.agent_id}
              onChange={(e) => setAgent(e.target.value)}
              className="border-input bg-card h-9 rounded-md border px-3 text-sm"
            >
              {data.agents.map((a) => (
                <option key={a.agent_id} value={a.agent_id}>
                  {a.agent_id} ({formatCount(a.open_cases)} open)
                </option>
              ))}
            </select>
          </div>
        )}
        <Button variant="outline" size="sm" onClick={queue.reload} className="ml-auto">
          <RotateCw aria-hidden /> Refresh
        </Button>
      </div>

      {queue.loading ? (
        <LoadingState label="Building the queue" rows={6} />
      ) : queue.error ? (
        <ErrorState message={queue.error} onRetry={queue.reload} />
      ) : data && (
        <div className="space-y-6">
          <section aria-label="Urgency tiers" className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
            {data.tiers
              .filter((t) => t.count > 0)
              .map((t) => (
                <button
                  key={t.key}
                  type="button"
                  onClick={() => setTier(tier === t.key ? "all" : t.key)}
                  aria-pressed={tier === t.key}
                  className={cn(
                    "bg-card rounded-lg border p-3 text-left transition-colors outline-none hover:border-primary/40 focus-visible:ring-[3px] focus-visible:ring-ring/40",
                    tier === t.key && "border-primary ring-primary/20 ring-2",
                  )}
                >
                  <div className="flex items-center justify-between gap-2">
                    <Badge variant={TIER_BADGE[t.key]}>{t.label}</Badge>
                    <span className="text-xl font-semibold tabular-nums">{formatCount(t.count)}</span>
                  </div>
                  <p className="text-muted-foreground mt-1.5 text-xs leading-snug">{t.rule}</p>
                </button>
              ))}
          </section>

          <p className="text-muted-foreground text-xs">
            Agent <span className="font-mono">{data.agent_id}</span> · {formatCount(data.total)} open cases · {data.ordering}
          </p>

          {items.length ? (
            <>
            <ol className="space-y-2.5 md:hidden" aria-label="Work queue in urgency order">
              {items.map((i) => (
                <li key={i.case_id} className="bg-card rounded-lg border p-3">
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <p className="font-medium">
                        <span className="text-muted-foreground mr-1.5 tabular-nums">{i.position}.</span>
                        <Link href={`/customers/${encodeURIComponent(i.customer_id)}`} className="underline-offset-4 hover:underline">
                          {i.name}
                        </Link>
                      </p>
                      <p className="text-muted-foreground font-mono text-xs">
                        {i.customer_id} · {i.product.replace(/_/g, " ")} · {i.dpd ?? "—"} DPD · {formatCad(i.overdue_cad)}
                      </p>
                    </div>
                    <Badge variant={TIER_BADGE[i.tier]}>{i.tier_label}</Badge>
                  </div>
                  <p className="mt-2 text-sm leading-snug">{i.reason}</p>
                  {i.flags.length > 0 && (
                    <div className="mt-1.5 flex flex-wrap gap-1">
                      {i.flags.map((f) => (
                        <Badge key={f} variant="outline" className="text-[0.7rem]">
                          {FLAG_LABEL[f] ?? f}
                        </Badge>
                      ))}
                    </div>
                  )}
                  <div className="mt-2 flex items-end justify-between gap-2 border-t pt-2 text-sm">
                    <div>
                      <span className="text-muted-foreground block text-xs">Next allowed contact</span>
                      <NextContact item={i} />
                    </div>
                    <div className="flex gap-1.5">
                      <Button asChild variant="outline" size="sm">
                        <Link href={`/briefs?customer=${encodeURIComponent(i.customer_id)}`} aria-label={`Prepare brief for ${i.name}`}>
                          Brief <ArrowRight aria-hidden />
                        </Link>
                      </Button>
                      <Button asChild size="sm">
                        <Link href={`/call/${encodeURIComponent(i.customer_id)}`} aria-label={`Start call with ${i.name}`}>
                          <PhoneCall aria-hidden /> Call
                        </Link>
                      </Button>
                    </div>
                  </div>
                </li>
              ))}
            </ol>
            <div className="hidden rounded-lg border md:block">
              <Table>
                <caption className="sr-only">Work queue in urgency order</caption>
                <TableHeader>
                  <TableRow className="hover:bg-transparent">
                    <TableHead scope="col" className="w-10">#</TableHead>
                    <TableHead scope="col">Customer</TableHead>
                    <TableHead scope="col">Why it is here</TableHead>
                    <TableHead scope="col">Next allowed contact</TableHead>
                    <TableHead scope="col" className="text-right">Overdue</TableHead>
                    <TableHead scope="col"><span className="sr-only">Brief and call</span></TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {items.map((i) => (
                    <TableRow key={i.case_id}>
                      <TableCell className="text-muted-foreground align-top tabular-nums">{i.position}</TableCell>
                      <TableCell className="align-top">
                        <Link href={`/customers/${encodeURIComponent(i.customer_id)}`} className="font-medium underline-offset-4 hover:underline">
                          {i.name}
                        </Link>
                        <span className="text-muted-foreground block font-mono text-xs">
                          {i.customer_id} · {i.product.replace(/_/g, " ")} · {i.dpd ?? "—"} DPD
                        </span>
                      </TableCell>
                      <TableCell className="max-w-[26rem] align-top whitespace-normal">
                        <Badge variant={TIER_BADGE[i.tier]} className="mb-1">
                          {i.tier_label}
                        </Badge>
                        <p className="text-sm leading-snug">{i.reason}</p>
                        {i.flags.length > 0 && (
                          <div className="mt-1 flex flex-wrap gap-1">
                            {i.flags.map((f) => (
                              <Badge key={f} variant="outline" className="text-[0.7rem]">
                                {FLAG_LABEL[f] ?? f}
                              </Badge>
                            ))}
                          </div>
                        )}
                      </TableCell>
                      <TableCell className="align-top text-sm">
                        <NextContact item={i} />
                      </TableCell>
                      <TableCell className="text-right align-top tabular-nums">{formatCad(i.overdue_cad)}</TableCell>
                      <TableCell className="align-top">
                        <div className="flex justify-end gap-1">
                          <Button asChild variant="ghost" size="sm">
                            <Link href={`/briefs?customer=${encodeURIComponent(i.customer_id)}`} aria-label={`Prepare brief for ${i.name}`}>
                              Brief <ArrowRight aria-hidden />
                            </Link>
                          </Button>
                          <Button asChild variant="outline" size="sm">
                            <Link href={`/call/${encodeURIComponent(i.customer_id)}`} aria-label={`Start call with ${i.name}`}>
                              <PhoneCall aria-hidden /> Call
                            </Link>
                          </Button>
                        </div>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
            </>
          ) : (
            <EmptyState title="No cases in this view" description="This agent has no open assigned cases in the selected tier." />
          )}
        </div>
      )}
    </>
  );
}

export default function QueuePage() {
  return (
    <>
      <PageHeader
        title="Work queue"
        description="Open cases in urgency order, with the reason for each position and the next time policy allows contact. The order is a fixed rule, not a model score."
      />
      <RoleGate section="queue">
        <QueueWorkspace />
      </RoleGate>
    </>
  );
}
