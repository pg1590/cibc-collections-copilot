"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { ArrowLeft, FileText, PhoneCall } from "lucide-react";
import { ContactCalendar, CustomerTimeline } from "@/components/customer-360";
import { PageHeader } from "@/components/page-header";
import { KeyValueList, RecordTable } from "@/components/record-table";
import { ErrorState, LoadingState } from "@/components/states";
import { VoiceEvidence } from "@/components/voice-evidence";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { canSee, useAuth } from "@/lib/auth";
import { useApi } from "@/lib/use-api";
import type { CustomerDetail } from "@/lib/types";
import { displayValue } from "@/lib/utils";

function safeDecode(value: string) {
  try {
    return decodeURIComponent(value);
  } catch {
    return value;
  }
}

function Section({ title, description, children }: { title: string; description: string; children: React.ReactNode }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        <CardDescription>{description}</CardDescription>
      </CardHeader>
      <CardContent>{children}</CardContent>
    </Card>
  );
}

export default function CustomerDetailPage() {
  const params = useParams<{ id: string }>();
  const id = safeDecode(params.id);
  const { session } = useAuth();
  const detail = useApi<CustomerDetail>(`/customers/${encodeURIComponent(id)}`);

  const back = (
    <Button asChild variant="ghost" size="sm" className="mb-4 -ml-2">
      <Link href="/customers">
        <ArrowLeft aria-hidden /> All customers
      </Link>
    </Button>
  );

  if (detail.loading) {
    return (
      <>
        {back}
        <LoadingState label="Loading customer" rows={5} />
      </>
    );
  }
  if (detail.error || !detail.data) {
    return (
      <>
        {back}
        <ErrorState message={detail.error ?? "No customer data returned."} onRetry={detail.reload} />
      </>
    );
  }

  const { customer, accounts, cases, identity, notes, features, snapshot_date } = detail.data;

  return (
    <>
      {back}
      <PageHeader
        title={customer.name}
        description={`Customer ${customer.customer_id} · data as of snapshot ${snapshot_date}`}
        actions={
          <>
            {canSee(session?.user.role, "briefs") && (
              <Button asChild variant={canSee(session?.user.role, "call") ? "outline" : "default"}>
                <Link href={`/briefs?customer=${encodeURIComponent(customer.customer_id)}`}>
                  <FileText aria-hidden /> Prepare agent brief
                </Link>
              </Button>
            )}
            {canSee(session?.user.role, "call") && (
              <Button asChild>
                <Link href={`/call/${encodeURIComponent(customer.customer_id)}`}>
                  <PhoneCall aria-hidden /> Start call
                </Link>
              </Button>
            )}
          </>
        }
      />

      <div className="space-y-6">
        <Card className="py-5">
          <CardContent>
            <dl className="grid gap-6 sm:grid-cols-4">
              {[
                ["Customer ID", customer.customer_id],
                ["Province", customer.province],
                ["Preferred language", customer.preferred_language],
                ["Identity confidence", customer.identity_confidence],
              ].map(([label, value]) => (
                <div key={label as string}>
                  <dt className="text-muted-foreground text-xs font-medium tracking-wide uppercase">{label}</dt>
                  <dd className="mt-1 font-medium break-words">{displayValue(value)}</dd>
                </div>
              ))}
            </dl>
          </CardContent>
        </Card>

        <Tabs defaultValue="history">
          <div className="-mx-1 overflow-x-auto px-1 pb-1">
            <TabsList>
              <TabsTrigger value="history">History &amp; contact</TabsTrigger>
              <TabsTrigger value="accounts">
                Accounts &amp; cases <span className="text-muted-foreground tabular-nums">{accounts.length + cases.length}</span>
              </TabsTrigger>
              <TabsTrigger value="identity">
                Identity <span className="text-muted-foreground tabular-nums">{identity.length}</span>
              </TabsTrigger>
              <TabsTrigger value="notes">Notes &amp; calls</TabsTrigger>
              <TabsTrigger value="features">Features</TabsTrigger>
            </TabsList>
          </div>
          <TabsContent value="history" className="space-y-6">
            <ContactCalendar customerId={customer.customer_id} />
            <CustomerTimeline customerId={customer.customer_id} />
          </TabsContent>
          <TabsContent value="accounts" className="grid gap-6 xl:grid-cols-2">
            <Section title="Accounts" description="Credit products held, with balances and delinquency.">
              <RecordTable records={accounts} caption="Accounts" emptyTitle="No accounts returned" />
            </Section>
            <Section title="Collections cases" description="Cases opened for this customer.">
              <RecordTable records={cases} caption="Cases" emptyTitle="No cases returned" />
            </Section>
          </TabsContent>
          <TabsContent value="identity">
            <Section
              title="Identity matching"
              description="Source-system records linked to this customer, with the method and evidence for each link. Confidence values are match scores, not calibrated probabilities."
            >
              <RecordTable records={identity} caption="Identity matching evidence" emptyTitle="No identity links returned" />
            </Section>
          </TabsContent>
          <TabsContent value="notes" className="space-y-6">
            <Section title="Notes and evidence" description="Agent notes and interaction evidence from source systems.">
              <RecordTable records={notes} caption="Notes" emptyTitle="No notes returned" />
            </Section>
            <VoiceEvidence key={customer.customer_id} customerId={customer.customer_id} />
          </TabsContent>
          <TabsContent value="features">
            <Section
              title="Features"
              description="Values from the feature store used by the brief. Protected attributes are never part of this set."
            >
              <KeyValueList data={features} emptyTitle="No features returned" />
            </Section>
          </TabsContent>
        </Tabs>

        <p className="text-muted-foreground flex items-center gap-2 text-xs">
          <Badge variant="outline">Synthetic</Badge> All records come from the synthetic hackathon dataset.
        </p>
      </div>
    </>
  );
}
