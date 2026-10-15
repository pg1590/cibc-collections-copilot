"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { CornerDownLeft, FileText, Phone, Search, User, type LucideIcon } from "lucide-react";
import { api } from "@/lib/api";
import { canSee, useAuth, type Section } from "@/lib/auth";
import type { CustomerList } from "@/lib/types";
import { cn } from "@/lib/utils";

type Item = { id: string; label: string; hint: string; href: string; icon: LucideIcon };

const PAGES: { label: string; href: string; section: Section; hint: string }[] = [
  { label: "Overview", href: "/overview", section: "overview", hint: "Portfolio totals and policy problems" },
  { label: "Work queue", href: "/queue", section: "queue", hint: "Cases in urgency order" },
  { label: "Customers", href: "/customers", section: "customers", hint: "Search the Customer 360" },
  { label: "Ask Collections", href: "/ask", section: "ask", hint: "Questions about the portfolio and policy" },
  { label: "Agent brief", href: "/briefs", section: "briefs", hint: "What to do, in order" },
  { label: "Supervisor review", href: "/reviews", section: "reviews", hint: "Approve, edit or reject" },
  { label: "Data & features", href: "/quality", section: "quality", hint: "Quality, features, model" },
];

export function CommandPalette({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const router = useRouter();
  const { session } = useAuth();
  const role = session?.user.role;
  const [query, setQuery] = useState("");
  const [customers, setCustomers] = useState<Item[]>([]);
  const [active, setActive] = useState(0);
  const input = useRef<HTMLInputElement>(null);

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        onOpenChange(!open);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onOpenChange]);

  useEffect(() => {
    if (open) {
      setQuery("");
      setActive(0);
      requestAnimationFrame(() => input.current?.focus());
    }
  }, [open]);

  useEffect(() => {
    const term = query.trim();
    if (!open || term.length < 2 || !canSee(role, "customers")) {
      setCustomers([]);
      return;
    }
    let live = true;
    const timer = setTimeout(() => {
      api<CustomerList>(`/customers?search=${encodeURIComponent(term)}&limit=6`)
        .then((result) => {
          if (!live) return;
          setCustomers(
            result.items.flatMap((c) => {
              const id = String(c.customer_id);
              const name = String(c.name ?? id);
              const rows: Item[] = [{ id: `c-${id}`, label: name, hint: `${id} · open customer`, href: `/customers/${encodeURIComponent(id)}`, icon: User }];
              if (canSee(role, "briefs"))
                rows.push({ id: `b-${id}`, label: `Brief: ${name}`, hint: "What to do, in order", href: `/briefs?customer=${encodeURIComponent(id)}`, icon: FileText });
              if (canSee(role, "call" as Section))
                rows.push({ id: `k-${id}`, label: `Call: ${name}`, hint: "Live call mode", href: `/call/${encodeURIComponent(id)}`, icon: Phone });
              return rows;
            }),
          );
        })
        .catch(() => live && setCustomers([]));
    }, 200);
    return () => {
      live = false;
      clearTimeout(timer);
    };
  }, [query, open, role]);

  const items = useMemo(() => {
    const term = query.trim().toLowerCase();
    const pages: Item[] = PAGES.filter((p) => canSee(role, p.section) && (!term || p.label.toLowerCase().includes(term))).map((p) => ({
      id: p.href,
      label: p.label,
      hint: p.hint,
      href: p.href,
      icon: CornerDownLeft,
    }));
    return [...customers, ...pages];
  }, [customers, query, role]);

  useEffect(() => setActive((a) => Math.min(a, Math.max(items.length - 1, 0))), [items.length]);

  function go(item: Item | undefined) {
    if (!item) return;
    onOpenChange(false);
    router.push(item.href);
  }

  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center bg-black/40 px-4 pt-[12vh]" onMouseDown={() => onOpenChange(false)}>
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Search pages and customers"
        className="bg-card w-full max-w-xl overflow-hidden rounded-xl border shadow-2xl"
        onMouseDown={(e) => e.stopPropagation()}
      >
        <div className="flex items-center gap-2 border-b px-4">
          <Search className="text-muted-foreground size-4" aria-hidden />
          <input
            ref={input}
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setActive(0);
            }}
            onKeyDown={(e) => {
              if (e.key === "Escape") onOpenChange(false);
              if (e.key === "ArrowDown") {
                e.preventDefault();
                setActive((a) => Math.min(a + 1, items.length - 1));
              }
              if (e.key === "ArrowUp") {
                e.preventDefault();
                setActive((a) => Math.max(a - 1, 0));
              }
              if (e.key === "Enter") go(items[active]);
            }}
            placeholder="Search a customer name or ID, or jump to a page…"
            className="h-12 flex-1 bg-transparent text-sm outline-none"
            role="combobox"
            aria-expanded="true"
            aria-controls="palette-results"
            aria-activedescendant={items[active] ? `palette-${items[active].id}` : undefined}
          />
          <kbd className="text-muted-foreground rounded border px-1.5 text-[0.75rem]">Esc</kbd>
        </div>
        <ul id="palette-results" role="listbox" data-lenis-prevent className="max-h-80 overflow-y-auto p-2">
          {items.length ? (
            items.map((item, i) => {
              const Icon = item.icon;
              return (
                <li
                  key={item.id}
                  id={`palette-${item.id}`}
                  role="option"
                  aria-selected={i === active}
                  onMouseEnter={() => setActive(i)}
                  onClick={() => go(item)}
                  className={cn("flex cursor-pointer items-center gap-3 rounded-md px-3 py-2", i === active ? "bg-accent text-accent-foreground" : "")}
                >
                  <Icon className="text-muted-foreground size-4 shrink-0" aria-hidden />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm font-medium">{item.label}</span>
                    <span className="text-muted-foreground block truncate text-xs">{item.hint}</span>
                  </span>
                </li>
              );
            })
          ) : (
            <li className="text-muted-foreground px-3 py-6 text-center text-sm">No matches. Try a customer ID like SAV-6847.</li>
          )}
        </ul>
        <div className="text-muted-foreground flex gap-4 border-t px-4 py-2 text-[0.75rem]">
          <span>↑↓ to move</span>
          <span>Enter to open</span>
          <span className="ml-auto">Ctrl K to toggle</span>
        </div>
      </div>
    </div>
  );
}
