"use client";

import { useState } from "react";
import { ChevronDown, Code2, Loader2, OctagonX, Send } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { RecordTable } from "@/components/record-table";
import { RoleGate } from "@/components/role-gate";
import { SourceList } from "@/components/source-list";
import { ErrorState } from "@/components/states";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { api, errorMessage } from "@/lib/api";
import type { AskResponse } from "@/lib/types";
import { displayValue, formatCount } from "@/lib/utils";

interface Exchange {
  question: string;
  result: AskResponse;
}

function AnswerCard({ question, result }: Exchange) {
  const calculationDetails = result.plan
    ? [
        { label: "Measure", value: result.plan.metric_id },
        { label: "Grouped by", value: result.plan.grouping },
        { label: "Start date", value: result.plan.start_date },
        { label: "Before", value: result.plan.end_date },
      ].filter(({ value }) => value !== undefined && value !== null && value !== "")
    : [];
  return (
    <Card>
      <CardHeader>
        <CardDescription>You asked</CardDescription>
        <CardTitle className="text-[1.05rem] leading-snug font-medium">{question}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-5">
        {result.generation && (
          <p className="text-muted-foreground text-sm">
            {result.generation.status === "generated" && result.generation.provider.toLowerCase() === "gemini"
              ? "Gemini-assisted answer based on recorded data and cited evidence."
              : result.generation.status === "fallback"
                ? "AI assistance was unavailable. This answer uses the recorded data and local sources."
                : "Answer prepared from the recorded data and local sources."}
          </p>
        )}
        {result.refused ? (
          <Alert variant="review">
            <OctagonX aria-hidden />
            <AlertTitle>Not answered</AlertTitle>
            <AlertDescription>
              <p>{result.reason || result.answer || "The question is outside what the system can answer from the data."}</p>
              {result.reason && result.answer && result.answer !== result.reason && <p>{result.answer}</p>}
            </AlertDescription>
          </Alert>
        ) : (
          <p className="text-[1.05rem] leading-relaxed whitespace-pre-line">{result.answer}</p>
        )}

        {!result.refused && result.explanation && (
          <section aria-label="Evidence explanation" className="bg-muted/40 rounded-lg border p-4">
            <h3 className="mb-2 text-sm font-medium">Evidence explanation</h3>
            <p className="text-sm leading-relaxed whitespace-pre-line">{result.explanation}</p>
          </section>
        )}

        <div className="text-muted-foreground flex flex-wrap gap-2 text-xs">
          <Badge variant="outline">Snapshot {result.snapshot_date}</Badge>
          <Badge variant="outline">{formatCount(result.execution_ms)} ms</Badge>
          {!result.refused && <Badge variant="outline">{formatCount(result.rows?.length ?? 0)} result rows</Badge>}
        </div>

        {!!calculationDetails.length && (
          <section aria-label="Calculation details" className="bg-muted/40 rounded-lg border p-3">
            <h3 className="mb-2 text-sm font-medium">Calculation details</h3>
            <dl className="flex flex-wrap gap-x-6 gap-y-3 text-sm">
              {calculationDetails.map(({ label, value }) => (
                <div key={label}>
                  <dt className="text-muted-foreground text-xs">{label}</dt>
                  <dd className="break-words">{typeof value === "string" ? value.replaceAll("_", " ") : displayValue(value)}</dd>
                </div>
              ))}
            </dl>
          </section>
        )}

        {result.sql_or_sources && (
          <Collapsible>
            <CollapsibleTrigger asChild>
              <Button variant="outline" size="sm" className="group">
                <Code2 aria-hidden /> SQL or sources used
                <ChevronDown className="transition-transform group-data-[state=open]:rotate-180" aria-hidden />
              </Button>
            </CollapsibleTrigger>
            <CollapsibleContent className="mt-3 space-y-3">
              <pre className="bg-sidebar text-sidebar-foreground overflow-x-auto rounded-lg p-4 font-mono text-xs leading-relaxed">
                <code>{result.sql_or_sources}</code>
              </pre>
            </CollapsibleContent>
          </Collapsible>
        )}

        {result.sources?.length > 0 && (
          <section aria-label="Answer sources" className="space-y-2">
            <h3 className="text-sm font-medium">Sources</h3>
            <SourceList sources={result.sources} />
          </section>
        )}

        {!result.refused && result.rows?.length > 0 && (
          <section aria-label="Result rows" className="space-y-2">
            <h3 className="text-sm font-medium">Result rows</h3>
            <RecordTable records={result.rows} caption="Query result rows" />
          </section>
        )}
      </CardContent>
    </Card>
  );
}

export default function AskPage() {
  const [question, setQuestion] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [history, setHistory] = useState<Exchange[]>([]);

  async function submit() {
    const text = question.trim();
    if (!text || pending) return;
    setPending(true);
    setError(null);
    try {
      const result = await api<AskResponse>("/ask", { method: "POST", body: JSON.stringify({ question: text }) });
      setHistory((h) => [{ question: text, result }, ...h]);
      setQuestion("");
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setPending(false);
    }
  }

  return (
    <>
      <PageHeader
        title="Ask Collections"
        description="Ask a plain-English question about the portfolio. Each answer shows the SQL or sources behind it. Questions the data cannot answer safely are refused, with a reason."
      />
      <RoleGate section="ask">
        <form
          className="mb-8 space-y-3"
          onSubmit={(e) => {
            e.preventDefault();
            void submit();
          }}
        >
          <Label htmlFor="question">Your question</Label>
          <Textarea
            id="question"
            rows={3}
            placeholder="For example: How many open cases are more than 90 days past due?"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
                e.preventDefault();
                void submit();
              }
            }}
            aria-describedby="question-help"
          />
          <div className="flex flex-wrap items-center justify-between gap-3">
            <p id="question-help" className="text-muted-foreground text-xs">
              Press Ctrl + Enter to send. Calculations use reviewed definitions, and each answer shows its evidence.
            </p>
            <Button type="submit" disabled={pending || !question.trim()}>
              {pending ? <Loader2 className="animate-spin" aria-hidden /> : <Send aria-hidden />}
              {pending ? "Answering…" : "Ask"}
            </Button>
          </div>
        </form>

        <div aria-live="polite" className="space-y-6">
          {error && <ErrorState title="The question could not be answered" message={error} />}
          {history.map((exchange, i) => (
            <AnswerCard key={history.length - i} {...exchange} />
          ))}
          {!history.length && !error && (
            <p className="text-muted-foreground text-sm">Answers appear here while you stay on this page. They are not stored.</p>
          )}
        </div>
      </RoleGate>
    </>
  );
}
