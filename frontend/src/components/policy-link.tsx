"use client";

import Link from "next/link";
import { BookOpen } from "lucide-react";
import { useLeaveGuard } from "@/lib/leave-guard";
import { citationHref, parseCitation } from "@/lib/policy-ref";
import { cn } from "@/lib/utils";

const VARIANTS = {
  // Same footprint as the teal badge it replaces.
  chip: "bg-accent text-accent-foreground hover:bg-seaglass rounded-md px-2 py-0.5 text-xs font-medium",
  // On the dark customer panel during a call.
  onDark: "rounded bg-white/15 px-1.5 py-0.5 text-[0.75rem] hover:bg-white/25",
  // Inside checklist text.
  inline: "text-muted-foreground hover:text-primary text-[0.75rem]",
};

/**
 * A policy citation that opens the Policies page at the cited section. Text that
 * is not a recognisable citation renders exactly as before, as plain text.
 */
export function PolicyLink({
  text,
  variant = "chip",
  className,
}: {
  text: string;
  variant?: keyof typeof VARIANTS;
  className?: string;
}) {
  const guard = useLeaveGuard();
  const citation = parseCitation(text);
  const look = cn("inline-flex items-center gap-1 font-mono break-words", VARIANTS[variant], className);
  if (!citation) return <span className={look}>{text}</span>;
  return (
    <Link
      href={citationHref(citation)}
      onClick={guard}
      aria-label={`Open ${text} in Policies`}
      title="Open the official text in Policies"
      className={cn(
        look,
        "underline-offset-2 transition-colors outline-none hover:underline focus-visible:ring-[3px] focus-visible:ring-ring/40",
      )}
    >
      <BookOpen className="size-3 shrink-0 opacity-70" aria-hidden />
      {text}
    </Link>
  );
}
