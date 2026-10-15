"use client";

import { CheckCircle2, Database, Layers, RotateCw, TriangleAlert } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { KeyValueList, RecordTable } from "@/components/record-table";
import { RoleGate } from "@/components/role-gate";
import { EmptyState, ErrorState, LoadingState } from "@/components/states";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useApi } from "@/lib/use-api";
import type { FeatureRegistry, QualityReport } from "@/lib/types";
import { formatCount, formatDateTime } from "@/lib/utils";

function severityVariant(severity: string) {
  const s = String(severity ?? "").toLowerCase();
  if (["critical", "error", "high"].includes(s)) return "destructive" as const;
  if (["warning", "warn", "medium"].includes(s)) return "review" as const;
  return "secondary" as const;
}

function QualityPanel() {
  const quality = useApi<QualityReport>("/quality");
  if (quality.loading) return <LoadingState label="Loading data quality report" rows={4} />;
  if (quality.error || !quality.data) return <ErrorState message={quality.error ?? "No report returned."} onRetry={quality.reload} />;
  const q = quality.data;
  const tables = Array.from(new Set([...Object.keys(q.raw_counts ?? {}), ...Object.keys(q.curated_counts ?? {})])).sort();
  const failing = q.checks.filter((c) => c.failed_rows > 0).length;

  return (
    <div className="space-y-8">
      <p className="text-muted-foreground text-sm">
        Snapshot <span className="text-foreground font-medium">{q.snapshot_date}</span> · pipeline built{" "}
        <span className="text-foreground font-medium">{formatDateTime(q.built_at)}</span>
      </p>

      <Card>
        <CardHeader>
          <CardTitle>Quality checks</CardTitle>
          <CardDescription>
            {q.checks.length
              ? `${formatCount(q.checks.length)} checks ran; ${formatCount(failing)} found failing rows.`
              : "Rules applied to the curated tables, with the rows that failed each one."}
          </CardDescription>
        </CardHeader>
        <CardContent>
          {q.checks.length ? (
            <div className="rounded-lg border">
              <Table>
                <caption className="sr-only">Data quality checks</caption>
                <TableHeader>
                  <TableRow className="hover:bg-transparent">
                    <TableHead scope="col">Check</TableHead>
                    <TableHead scope="col">Table</TableHead>
                    <TableHead scope="col" className="text-right">
                      Failed rows
                    </TableHead>
                    <TableHead scope="col" className="text-right">
                      Total rows
                    </TableHead>
                    <TableHead scope="col" className="text-right">
                      Failure rate
                    </TableHead>
                    <TableHead scope="col">Severity</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {q.checks.map((c, i) => (
                    <TableRow key={`${c.table}-${c.check}-${i}`}>
                      <TableCell className="font-medium">
                        <span className="flex items-center gap-2">
                          {c.failed_rows > 0 ? (
                            <TriangleAlert className="text-review size-4 shrink-0" aria-label="Has failures" />
                          ) : (
                            <CheckCircle2 className="text-success size-4 shrink-0" aria-label="Passed" />
                          )}
                          {c.check}
                        </span>
                      </TableCell>
                      <TableCell className="font-mono text-xs">{c.table}</TableCell>
                      <TableCell className="text-right tabular-nums">{formatCount(c.failed_rows)}</TableCell>
                      <TableCell className="text-right tabular-nums">{formatCount(c.total_rows)}</TableCell>
                      <TableCell className="text-right tabular-nums">
                        {c.total_rows > 0 ? `${((c.failed_rows / c.total_rows) * 100).toFixed(2)}%` : "—"}
                      </TableCell>
                      <TableCell>
                        <Badge variant={severityVariant(c.severity)}>{c.severity}</Badge>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          ) : (
            <EmptyState title="No checks reported" />
          )}
        </CardContent>
      </Card>

      <div className="grid gap-6 xl:grid-cols-[1.3fr_1fr] [&>*]:min-w-0">
        <Card>
          <CardHeader>
            <CardTitle>Row counts</CardTitle>
            <CardDescription>Rows read from source files (raw) and rows kept after cleaning (curated).</CardDescription>
          </CardHeader>
          <CardContent>
            {tables.length ? (
              <div className="rounded-lg border">
                <Table>
                  <caption className="sr-only">Raw and curated row counts</caption>
                  <TableHeader>
                    <TableRow className="hover:bg-transparent">
                      <TableHead scope="col">Table</TableHead>
                      <TableHead scope="col" className="text-right">
                        Raw
                      </TableHead>
                      <TableHead scope="col" className="text-right">
                        Curated
                      </TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {tables.map((t) => (
                      <TableRow key={t}>
                        <TableCell className="font-mono text-xs">{t}</TableCell>
                        <TableCell className="text-right tabular-nums">{formatCount(q.raw_counts?.[t])}</TableCell>
                        <TableCell className="text-right tabular-nums">{formatCount(q.curated_counts?.[t])}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            ) : (
              <EmptyState title="No table counts reported" />
            )}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Identity resolution</CardTitle>
            <CardDescription>Summary from the matching step across the five source systems.</CardDescription>
          </CardHeader>
          <CardContent>
            <KeyValueList data={q.identity} emptyTitle="No identity summary reported" />
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function FeaturesPanel() {
  const features = useApi<FeatureRegistry>("/features");
  if (features.loading) return <LoadingState label="Loading feature registry" rows={4} />;
  if (features.error || !features.data) return <ErrorState message={features.error ?? "No registry returned."} onRetry={features.reload} />;
  const f = features.data;
  const parityOk = f.parity.checked > 0 && f.parity.mismatches === 0;

  return (
    <div className="space-y-8">
      <div className="grid gap-4 sm:grid-cols-3">
        <Card className="gap-1 py-5">
          <CardContent>
            <p className="text-muted-foreground text-sm">Registry version</p>
            <p className="mt-1 font-mono text-lg font-semibold break-words">{f.version}</p>
          </CardContent>
        </Card>
        <Card className="gap-1 py-5">
          <CardContent>
            <p className="text-muted-foreground text-sm">Parity comparisons run</p>
            <p className="mt-1 text-2xl font-semibold tabular-nums">{formatCount(f.parity.checked)}</p>
          </CardContent>
        </Card>
        <Card className="gap-1 py-5">
          <CardContent>
            <p className="text-muted-foreground text-sm">Offline vs. live mismatches</p>
            <p className="mt-1 flex items-center gap-2 text-2xl font-semibold tabular-nums">
              {formatCount(f.parity.mismatches)}
              {f.parity.checked === 0 ? (
                <Badge variant="review">Not checked yet</Badge>
              ) : parityOk ? (
                <Badge variant="success">Parity holds</Badge>
              ) : (
                <Badge variant="destructive">Mismatch</Badge>
              )}
            </p>
          </CardContent>
        </Card>
      </div>
      <p className="text-muted-foreground text-sm">
        Parity means the same feature code gives the same values in the offline (training) path and the live (brief) path.
        These numbers are the result of an actual comparison run by the backend.
      </p>

      <Card>
        <CardHeader>
          <CardTitle>Feature definitions</CardTitle>
          <CardDescription>Every feature the model and briefs can use.</CardDescription>
        </CardHeader>
        <CardContent>
          <RecordTable records={f.definitions} caption="Feature definitions" emptyTitle="No feature definitions registered" />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Model</CardTitle>
          <CardDescription>Model metadata reported by the backend.</CardDescription>
        </CardHeader>
        <CardContent>
          <KeyValueList data={f.model} emptyTitle="No model metadata reported" />
        </CardContent>
      </Card>
    </div>
  );
}

export default function QualityPage() {
  return (
    <>
      <PageHeader
        title="Data quality and features"
        description="What the pipeline checked, what failed, and which features are registered for the model. All figures come from the latest pipeline run."
        actions={
          <Button variant="outline" size="sm" onClick={() => window.location.reload()}>
            <RotateCw aria-hidden /> Reload
          </Button>
        }
      />
      <RoleGate section="quality">
        <Tabs defaultValue="quality">
          <TabsList aria-label="Choose report">
            <TabsTrigger value="quality">
              <Database aria-hidden /> Data quality
            </TabsTrigger>
            <TabsTrigger value="features">
              <Layers aria-hidden /> Feature registry
            </TabsTrigger>
          </TabsList>
          <TabsContent value="quality">
            <QualityPanel />
          </TabsContent>
          <TabsContent value="features">
            <FeaturesPanel />
          </TabsContent>
        </Tabs>
      </RoleGate>
    </>
  );
}
