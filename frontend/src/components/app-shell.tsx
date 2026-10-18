"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useRef, useState } from "react";
import { CircleAlert, LogOut, Search } from "lucide-react";
import { CommandPalette } from "@/components/command-palette";
import { useAutoReveal, useSmoothScroll } from "@/components/motion/reveal";
import { BrandMark } from "@/components/landing/brand-mark";
import { SiteFooter } from "@/components/site-footer";
import { canSee, useAuth, type Section } from "@/lib/auth";
import { useApi } from "@/lib/use-api";
import type { Health } from "@/lib/types";
import { cn } from "@/lib/utils";

// Short, plain labels so the whole bar fits on one line on a laptop.
const NAV: { href: string; label: string; section: Section }[] = [
  { href: "/overview", label: "Overview", section: "overview" },
  { href: "/queue", label: "Work queue", section: "queue" },
  { href: "/customers", label: "Customers", section: "customers" },
  { href: "/ask", label: "Ask", section: "ask" },
  { href: "/briefs", label: "Briefs", section: "briefs" },
  { href: "/reviews", label: "Reviews", section: "reviews" },
  { href: "/quality", label: "Data", section: "quality" },
  { href: "/policies", label: "Policies", section: "policies" },
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const { session, logout } = useAuth();
  const health = useApi<Health>("/health");
  const [palette, setPalette] = useState(false);
  const mainRef = useRef<HTMLElement>(null);
  useSmoothScroll();
  useAutoReveal(mainRef, pathname);
  const role = session?.user.role;
  const items = NAV.filter((item) => canSee(role, item.section));

  // Only speak up when something is wrong; a healthy backend needs no badge.
  const problem = health.error ? "Backend unreachable" : health.data && !health.data.dataset_ready ? "Dataset not ready" : null;

  // Tables and dashboards get the full bar width; reading pages keep shorter lines.
  const width = pathname.startsWith("/call/")
    ? "max-w-[100rem] pb-0 sm:pb-0"
    : ["/ask", "/briefs", "/reviews", "/policies"].some((p) => pathname.startsWith(p))
      ? "max-w-6xl"
      : "max-w-7xl";

  const links = items.map(({ href, label }) => {
      const active = pathname === href || pathname.startsWith(`${href}/`);
      return (
        <Link
          key={href}
          href={href}
          aria-current={active ? "page" : undefined}
          className={cn(
            "shrink-0 rounded-full px-3.5 py-1.5 text-[0.9375rem] whitespace-nowrap transition-colors outline-none focus-visible:ring-[3px] focus-visible:ring-chrome-accent/60",
            active
              ? "bg-chrome-accent text-chrome font-medium"
              : "text-chrome-muted hover:text-chrome-foreground hover:bg-white/8",
          )}
        >
          {label}
        </Link>
      );
    });

  return (
    <div className="flex min-h-dvh flex-col">
      <a
        href="#main"
        className="focus:bg-card sr-only z-50 rounded-md px-3 py-2 focus:not-sr-only focus:fixed focus:top-3 focus:left-3"
      >
        Skip to content
      </a>
      <CommandPalette open={palette} onOpenChange={setPalette} />

      <header className="app-header sticky top-0 z-30">
        <div className="mx-auto flex h-16 max-w-7xl items-center gap-4 px-4 sm:px-8">
          <Link
            href="/overview"
            className="flex shrink-0 items-center gap-2.5 rounded-lg whitespace-nowrap outline-none focus-visible:ring-[3px] focus-visible:ring-chrome-accent/60"
          >
            <BrandMark tone="dark" />
            <span className="text-chrome-foreground hidden text-[1.0625rem] font-medium sm:inline lg:hidden xl:inline">Collections Copilot</span>
          </Link>

          <nav aria-label="Main" className="hidden min-w-0 flex-1 items-center justify-center gap-0.5 overflow-x-auto [scrollbar-width:none] lg:flex xl:gap-1">
            {links}
          </nav>

          <div className="ml-auto flex shrink-0 items-center gap-2 whitespace-nowrap lg:ml-0">
            {problem && (
              <span role="status" className="bg-review-soft text-review-foreground inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-sm">
                <CircleAlert className="size-4" aria-hidden />
                <span className="hidden sm:inline">{problem}</span>
                <span className="sr-only sm:hidden">{problem}</span>
              </span>
            )}
            <button
              type="button"
              onClick={() => setPalette(true)}
              className="text-chrome-muted hover:text-chrome-foreground flex h-9 shrink-0 items-center gap-2 rounded-full bg-white/8 px-3 text-sm ring-1 ring-white/12 transition-colors outline-none hover:bg-white/14 focus-visible:ring-[3px] focus-visible:ring-chrome-accent/60"
              aria-label="Search customers and pages (Ctrl K)"
            >
              <Search className="size-4" aria-hidden />
              <span className="hidden xl:inline">Search</span>
              <kbd className="text-chrome-muted/80 hidden font-sans text-xs xl:inline">Ctrl K</kbd>
            </button>
            <span
              title={`Signed in as ${session?.user.username} (${role})`}
              className="bg-chrome-accent text-chrome ml-1 grid size-9 shrink-0 place-items-center rounded-full text-sm font-medium uppercase"
            >
              <span aria-hidden>{session?.user.username.slice(0, 1)}</span>
              <span className="sr-only">
                Signed in as {session?.user.username} ({role})
              </span>
            </span>
            <button
              type="button"
              onClick={logout}
              className="text-chrome-muted hover:text-chrome-foreground flex h-9 shrink-0 items-center gap-1.5 rounded-full px-3 text-sm transition-colors outline-none hover:bg-white/8 focus-visible:ring-[3px] focus-visible:ring-chrome-accent/60"
            >
              <LogOut className="size-4" aria-hidden />
              <span className="hidden sm:inline">Sign out</span>
              <span className="sr-only sm:hidden">Sign out</span>
            </button>
          </div>
        </div>

        {/* Below lg the same links scroll sideways under the brand row. */}
        <nav aria-label="Main" className="mx-auto flex max-w-7xl gap-2 overflow-x-auto px-4 pb-2.5 [scrollbar-width:none] sm:px-8 lg:hidden">
          {links}
        </nav>
      </header>

      <main
        ref={mainRef}
        id="main"
        tabIndex={-1}
        className={cn(
          "mx-auto w-full flex-1 px-4 py-10 outline-none sm:px-8 sm:py-14",
          width,
        )}
      >
        {children}
      </main>
      <SiteFooter links={items} className="mt-10" />
    </div>
  );
}
