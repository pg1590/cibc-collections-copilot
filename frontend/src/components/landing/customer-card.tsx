import { cn } from "@/lib/utils";
import styles from "./landing.module.css";

/**
 * An illustrative customer, not a record from the dataset: the welcome page is
 * shown before sign-in, so it never displays real (even synthetic) customer data.
 * Each source matches one of the six systems the data build links by identity.
 */
export const SOURCES = [
  { id: "crm", system: "CRM", fact: "Prefers French" },
  { id: "cards", system: "Cards", fact: "$1,240.00 past due" },
  { id: "core", system: "Core banking", fact: "Overdraft, 61 days" },
  { id: "lending", system: "Lending", fact: "Auto loan, 86 days" },
  { id: "bureau", system: "Credit bureau", fact: "Identity match 0.97" },
  { id: "collections", system: "Collections", fact: "Note: “my hours were cut”" },
] as const;

export type SourceId = (typeof SOURCES)[number]["id"];

const WRITE_OFF_DAYS = 180;
const ACCOUNTS: { source: SourceId; product: string; days: number; amount: string }[] = [
  { source: "cards", product: "Credit card", days: 34, amount: "$1,240.00" },
  { source: "core", product: "Overdraft", days: 61, amount: "$312.40" },
  { source: "lending", product: "Auto loan", days: 86, amount: "$1,866.75" },
];

const order = (id: SourceId) => SOURCES.findIndex((s) => s.id === id);

function Row({ source, className, children }: { source: SourceId; className?: string; children: React.ReactNode }) {
  return (
    <div data-source={source} className={cn(styles.row, className)} style={{ "--i": order(source) } as React.CSSProperties}>
      {children}
    </div>
  );
}

export function CustomerCard({ className, ref }: { className?: string; ref?: React.Ref<HTMLElement> }) {
  return (
    <figure
      ref={ref}
      className={cn(
        styles.card,
        "bg-paper border-line-soft w-full max-w-[25rem] rounded-[1.25rem] border p-5 tabular-nums sm:p-6",
        className,
      )}
    >
      <figcaption className="sr-only">
        Illustration: one customer&apos;s records from six bank systems combined into a single view, with a suggested
        next step that a supervisor reviews.
      </figcaption>
      <div aria-hidden>
        <div className="flex items-start justify-between gap-3">
          <p className="text-slate text-sm">Illustrative customer</p>
          <p className="bg-seaglass/70 text-ink-soft rounded-full px-2.5 py-0.5 text-xs">6 systems linked</p>
        </div>
        <p className="text-ink-soft mt-1 text-[1.375rem] leading-tight font-medium">Élise Tremblay</p>
        <Row source="crm" className="text-slate mt-0.5 text-sm">
          Montréal, prefers French
        </Row>

        <div className="border-line-soft mt-4 border-t pt-4">
          <div className="flex items-baseline justify-between">
            <p className="text-slate text-sm">Overdue across 3 accounts</p>
            <p className="text-ink-soft text-lg font-medium">$3,419.15</p>
          </div>
          <ul className="mt-3 space-y-2.5">
            {ACCOUNTS.map(({ source, product, days, amount }) => (
              <li key={source}>
                <Row source={source}>
                  <div className="flex items-baseline justify-between text-sm">
                    <span className="text-ink-soft">{product}</span>
                    <span className="text-slate">
                      {days} days, {amount}
                    </span>
                  </div>
                  {/* Distance travelled toward the 180-day write-off point. */}
                  <div className="bg-mist mt-1.5 h-1.5 overflow-hidden rounded-full">
                    <div
                      className={cn(styles.bar, "bg-seaglass-deep h-full rounded-full")}
                      style={{ width: `${(days / WRITE_OFF_DAYS) * 100}%` }}
                    />
                  </div>
                </Row>
              </li>
            ))}
          </ul>
          <p className="text-slate mt-1.5 text-right text-xs">Bars show days past due, out of 180</p>
        </div>

        <div className="border-line-soft mt-4 space-y-2 border-t pt-4 text-sm">
          <Row source="bureau" className="flex justify-between">
            <span className="text-slate">Identity match</span>
            <span className="text-ink-soft">0.97, confirmed</span>
          </Row>
          <Row source="collections" className="flex justify-between gap-4">
            <span className="text-slate shrink-0">Latest note</span>
            <span className="text-ink-soft text-right">&ldquo;my hours were cut&rdquo;</span>
          </Row>
        </div>

        <div className={cn(styles.plan, "bg-seaglass/55 mt-4 rounded-xl px-4 py-3")}>
          <p className="text-ink-soft text-sm font-medium">Next step: offer a reduced-payment plan</p>
          <p className="text-slate mt-0.5 text-xs leading-relaxed">
            Possible hardship in the latest note. The draft waits for a supervisor before anything is sent.
          </p>
        </div>
      </div>
    </figure>
  );
}
