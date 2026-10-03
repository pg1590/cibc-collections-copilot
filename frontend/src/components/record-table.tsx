import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { EmptyState } from "@/components/states";
import { displayValue, humanize } from "@/lib/utils";
import type { ApiRecord } from "@/lib/types";

/**
 * Shows records exactly as returned by the API. Columns come from the
 * records themselves, so nothing is assumed about fields the contract leaves open.
 */
export function RecordTable({
  records,
  caption,
  emptyTitle = "No records",
  emptyDescription,
}: {
  records: ApiRecord[];
  caption?: string;
  emptyTitle?: string;
  emptyDescription?: string;
}) {
  if (!records.length) return <EmptyState title={emptyTitle} description={emptyDescription} />;
  const columns = Array.from(new Set(records.flatMap((r) => Object.keys(r))));
  return (
    <div className="rounded-lg border">
      <Table>
        {caption && <caption className="sr-only">{caption}</caption>}
        <TableHeader>
          <TableRow className="hover:bg-transparent">
            {columns.map((c) => (
              <TableHead key={c} scope="col">
                {humanize(c)}
              </TableHead>
            ))}
          </TableRow>
        </TableHeader>
        <TableBody>
          {records.map((record, i) => (
            <TableRow key={i}>
              {columns.map((c) => (
                <TableCell key={c} className="max-w-[28rem] align-top break-words">
                  {displayValue(record[c])}
                </TableCell>
              ))}
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}

export function KeyValueList({ data, emptyTitle = "Nothing reported" }: { data: ApiRecord | null | undefined; emptyTitle?: string }) {
  const entries = Object.entries(data ?? {});
  if (!entries.length) return <EmptyState title={emptyTitle} />;
  return (
    <dl className="grid gap-x-8 gap-y-3 sm:grid-cols-2">
      {entries.map(([key, value]) => (
        <div key={key} className="border-b pb-2">
          <dt className="text-muted-foreground text-xs font-medium tracking-wide uppercase">{humanize(key)}</dt>
          <dd className="mt-1 text-sm break-words">{displayValue(value)}</dd>
        </div>
      ))}
    </dl>
  );
}
