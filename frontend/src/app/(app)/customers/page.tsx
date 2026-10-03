"use client";

import Link from "next/link";
import { useState } from "react";
import { ChevronRight, Search } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { EmptyState, ErrorState, LoadingState } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useAuth } from "@/lib/auth";
import { useApi } from "@/lib/use-api";
import type { CustomerList } from "@/lib/types";
import { displayValue, formatCad, formatCount } from "@/lib/utils";

const LIMIT = 20;

export default function CustomersPage() {
  const { session } = useAuth();
  const [draft, setDraft] = useState("");
  const [search, setSearch] = useState("");
  const list = useApi<CustomerList>(`/customers?search=${encodeURIComponent(search)}&limit=${LIMIT}`);

  return (
    <>
      <PageHeader
        title="Customers"
        description={
          session?.user.role === "agent"
            ? "Customers on your assigned cases. Open one to see accounts, cases and how their records were matched."
            : "Search the golden customer view by name or ID. Open a customer to see accounts, cases and matching evidence."
        }
      />

      <form
        role="search"
        className="mb-6 flex flex-col gap-2 sm:flex-row sm:items-end"
        onSubmit={(e) => {
          e.preventDefault();
          setSearch(draft.trim());
        }}
      >
        <div className="flex-1 space-y-2">
          <Label htmlFor="customer-search">Search customers</Label>
          <Input
            id="customer-search"
            type="search"
            placeholder="Name or customer ID"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
          />
        </div>
        <Button type="submit">
          <Search aria-hidden /> Search
        </Button>
      </form>

      {list.loading ? (
        <LoadingState label="Loading customers" rows={5} />
      ) : list.error ? (
        <ErrorState message={list.error} onRetry={list.reload} />
      ) : !list.data?.items.length ? (
        <EmptyState
          title={search ? `No customers match “${search}”` : "No customers to show"}
          description={search ? "Try a different name or ID." : "The pipeline returned no customers for your role."}
        />
      ) : (
        <>
          <p className="text-muted-foreground mb-3 text-sm" aria-live="polite">
            Showing {formatCount(list.data.items.length)} of {formatCount(list.data.total)} customer{list.data.total === 1 ? "" : "s"}
            {search && <> matching “{search}”</>}.
          </p>
          <div className="bg-card rounded-xl border">
            <Table>
              <caption className="sr-only">Customers</caption>
              <TableHeader>
                <TableRow className="hover:bg-transparent">
                  <TableHead scope="col">Customer</TableHead>
                  <TableHead scope="col">Province</TableHead>
                  <TableHead scope="col" className="text-right">
                    Open cases
                  </TableHead>
                  <TableHead scope="col" className="text-right">
                    Overdue
                  </TableHead>
                  <TableHead scope="col" className="text-right">
                    Max days past due
                  </TableHead>
                  <TableHead scope="col">Identity match</TableHead>
                  <TableHead scope="col">
                    <span className="sr-only">Open</span>
                  </TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {list.data.items.map((c) => (
                  <TableRow key={c.customer_id}>
                    <TableCell>
                      <Link
                        href={`/customers/${encodeURIComponent(c.customer_id)}`}
                        className="font-medium underline-offset-4 outline-none hover:underline focus-visible:underline"
                      >
                        {c.name}
                      </Link>
                      <p className="text-muted-foreground font-mono text-xs">{c.customer_id}</p>
                    </TableCell>
                    <TableCell>{c.province}</TableCell>
                    <TableCell className="text-right tabular-nums">{formatCount(c.open_cases)}</TableCell>
                    <TableCell className="text-right tabular-nums">{formatCad(c.total_overdue)}</TableCell>
                    <TableCell className="text-right tabular-nums">{formatCount(c.max_dpd)}</TableCell>
                    <TableCell>{displayValue(c.identity_confidence)}</TableCell>
                    <TableCell className="w-8">
                      <ChevronRight className="text-muted-foreground size-4" aria-hidden />
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </>
      )}
    </>
  );
}
