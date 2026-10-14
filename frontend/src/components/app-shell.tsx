"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import {
  ClipboardCheck,
  ListOrdered,
  Database,
  FileText,
  LayoutDashboard,
  LogOut,
  Menu,
  MessageSquareText,
  Search,
  Users,
  X,
  type LucideIcon,
} from "lucide-react";
import { CommandPalette } from "@/components/command-palette";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { canSee, useAuth, type Section } from "@/lib/auth";
import { useApi } from "@/lib/use-api";
import type { Health } from "@/lib/types";
import { cn } from "@/lib/utils";

const NAV: { href: string; label: string; icon: LucideIcon; section: Section }[] = [
  { href: "/overview", label: "Overview", icon: LayoutDashboard, section: "overview" },
  { href: "/queue", label: "Work queue", icon: ListOrdered, section: "queue" },
  { href: "/customers", label: "Customers", icon: Users, section: "customers" },
  { href: "/ask", label: "Ask Collections", icon: MessageSquareText, section: "ask" },
  { href: "/briefs", label: "Agent brief", icon: FileText, section: "briefs" },
  { href: "/reviews", label: "Supervisor review", icon: ClipboardCheck, section: "reviews" },
  { href: "/quality", label: "Data & features", icon: Database, section: "quality" },
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const { session, logout } = useAuth();
  const health = useApi<Health>("/health");
  const [open, setOpen] = useState(false);
  const [palette, setPalette] = useState(false);
  const role = session?.user.role;

  const nav = (
    <nav aria-label="Main" className="flex flex-col gap-1">
      {NAV.filter((item) => canSee(role, item.section)).map(({ href, label, icon: Icon }) => {
        const active = pathname === href || pathname.startsWith(`${href}/`);
        return (
          <Link
            key={href}
            href={href}
            onClick={() => setOpen(false)}
            aria-current={active ? "page" : undefined}
            className={cn(
              "flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors outline-none focus-visible:ring-2 focus-visible:ring-teal-300",
              active ? "bg-sidebar-accent font-medium text-white" : "text-sidebar-foreground/85 hover:bg-sidebar-accent/60 hover:text-white",
            )}
          >
            <Icon className={cn("size-4", active ? "text-teal-300" : "text-sidebar-muted")} aria-hidden />
            {label}
          </Link>
        );
      })}
    </nav>
  );

  return (
    <div className="min-h-dvh lg:grid lg:grid-cols-[16.5rem_1fr]">
      <a
        href="#main"
        className="focus:bg-card sr-only z-50 rounded-md px-3 py-2 focus:not-sr-only focus:fixed focus:top-3 focus:left-3"
      >
        Skip to content
      </a>

      <aside
        className={cn(
          "bg-sidebar text-sidebar-foreground fixed inset-y-0 left-0 z-40 flex w-[16.5rem] flex-col px-4 py-6 transition-transform lg:sticky lg:top-0 lg:h-dvh lg:translate-x-0",
          open ? "translate-x-0" : "-translate-x-full",
        )}
      >
        <div className="mb-8 flex items-start justify-between px-2">
          <div>
            <p className="text-[1.05rem] font-semibold tracking-tight text-white">Collections Copilot</p>
            <p className="text-sidebar-muted mt-0.5 text-xs">by team Adda Wale</p>
          </div>
          <button
            type="button"
            className="text-sidebar-muted rounded p-1 hover:text-white lg:hidden"
            onClick={() => setOpen(false)}
            aria-label="Close menu"
          >
            <X className="size-5" />
          </button>
        </div>
        {nav}
        <div className="border-sidebar-accent mt-auto space-y-2 border-t px-2 pt-4 text-xs">
          <p className="text-sidebar-muted">Synthetic hackathon data only. Approvals record a decision and never contact customers.</p>
        </div>
      </aside>
      {open && <div className="fixed inset-0 z-30 bg-black/30 lg:hidden" onClick={() => setOpen(false)} aria-hidden />}

      <div className="flex min-w-0 flex-col">
        <header className="bg-background/90 sticky top-0 z-20 flex flex-wrap items-center gap-3 border-b px-4 py-3 backdrop-blur sm:px-8">
          <Button variant="ghost" size="icon" className="lg:hidden" onClick={() => setOpen(true)} aria-label="Open menu">
            <Menu />
          </Button>
          <div className="flex flex-wrap items-center gap-2 text-xs" aria-label="Environment">
            <Badge variant="teal">Synthetic data</Badge>
            {health.data ? (
              <>
                <Badge variant="outline">Snapshot {health.data.snapshot_date ?? "not set"}</Badge>
                <Badge variant="outline">Runtime: {health.data.runtime_mode}</Badge>
                {!health.data.dataset_ready && <Badge variant="review">Dataset not ready</Badge>}
              </>
            ) : health.error ? (
              <Badge variant="destructive">Backend unreachable</Badge>
            ) : (
              <Badge variant="outline">Checking backend…</Badge>
            )}
          </div>
          <button
            type="button"
            onClick={() => setPalette(true)}
            className="bg-card text-muted-foreground hover:border-primary/40 ml-auto flex h-9 items-center gap-2 rounded-md border px-3 text-sm transition-colors outline-none focus-visible:ring-[3px] focus-visible:ring-ring/40 sm:w-64"
            aria-label="Search customers and pages (Ctrl K)"
          >
            <Search className="size-4" aria-hidden />
            <span className="hidden sm:inline">Search customers…</span>
            <kbd className="ml-auto hidden rounded border px-1.5 text-[0.65rem] sm:inline">Ctrl K</kbd>
          </button>
          <div className="flex items-center gap-3">
            <div className="text-right text-sm leading-tight">
              <p className="font-medium">{session?.user.username}</p>
              <p className="text-muted-foreground text-xs capitalize">{role}</p>
            </div>
            <Button variant="outline" size="sm" onClick={logout}>
              <LogOut aria-hidden /> Sign out
            </Button>
          </div>
        </header>
        <CommandPalette open={palette} onOpenChange={setPalette} />
        <main
          id="main"
          tabIndex={-1}
          className={cn(
            "mx-auto w-full flex-1 px-4 py-8 outline-none sm:px-8 sm:py-10",
            pathname.startsWith("/call/") ? "max-w-[100rem] pb-0 sm:pb-0" : "max-w-6xl",
          )}
        >
          {children}
        </main>
      </div>
    </div>
  );
}
