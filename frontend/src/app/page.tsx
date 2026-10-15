"use client";

import Link from "next/link";
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { BarChart3, Headset, ShieldCheck, type LucideIcon } from "lucide-react";
import { BrandMark } from "@/components/landing/brand-mark";
import { CustomerCard, SOURCES } from "@/components/landing/customer-card";
import { SiteFooter } from "@/components/site-footer";
import styles from "@/components/landing/landing.module.css";
import { useAuth } from "@/lib/auth";
import type { Role } from "@/lib/types";
import { cn } from "@/lib/utils";

type Phase = "hidden" | "scatter" | "gather" | "plan" | "settle" | "done";

// Milliseconds from the start of the intro at which each phase begins.
const TIMELINE: [Phase, number][] = [
  ["scatter", 60],
  ["gather", 1350],
  ["plan", 2650],
  ["settle", 3450],
  ["done", 4500],
];

// Where each slip starts, as a fraction of the viewport from its centre.
const SCATTER: [number, number, number][] = [
  [-0.3, -0.3, -3],
  [0.29, -0.33, 2.5],
  [-0.34, 0.0, 2],
  [0.33, 0.02, -2],
  [-0.25, 0.31, -1.5],
  [0.26, 0.29, 3],
];

const ROLES: { role: Role; title: string; text: string; icon: LucideIcon }[] = [
  { role: "analyst", title: "Analyst", text: "Ask questions about the portfolio and see where every number came from.", icon: BarChart3 },
  { role: "agent", title: "Agent", text: "Work your queue and run calls with a plan that updates as you talk.", icon: Headset },
  { role: "supervisor", title: "Supervisor", text: "Approve or change drafts, and see who did what in the audit log.", icon: ShieldCheck },
];

type Slip = { x: number; y: number; r: number; tx: number; ty: number };

// Lives only as long as the loaded page: every reload or fresh visit plays the
// intro again, while returning here from inside the app (for example "Back to
// home" on the sign-in page) does not replay it.
let introSeen = false;

function introAlreadySeen() {
  return introSeen;
}

function markIntroSeen() {
  introSeen = true;
}

export default function WelcomePage() {
  const { session, ready } = useAuth();
  const [phase, setPhase] = useState<Phase>("hidden");
  const [slips, setSlips] = useState<Slip[] | null>(null);
  const [offset, setOffset] = useState({ dx: 0, dy: 0 });
  const cardRef = useRef<HTMLElement>(null);
  const timers = useRef<number[]>([]);

  const finish = useCallback(() => {
    timers.current.forEach(window.clearTimeout);
    timers.current = [];
    markIntroSeen();
    setPhase("done");
  }, []);

  // Decide before first paint whether to play, and measure where the card must start.
  useLayoutEffect(() => {
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const card = cardRef.current;
    if (reduced || introAlreadySeen() || !card) {
      setPhase("done");
      return;
    }
    window.scrollTo(0, 0);
    const rect = card.getBoundingClientRect();
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    setOffset({ dx: vw / 2 - (rect.left + rect.width / 2), dy: vh / 2 - (rect.top + rect.height / 2) });
    // Keep every slip fully on screen, including on a phone.
    const halfW = Math.min(vw * 0.23, 108) + 12;
    setSlips(
      SCATTER.map(([fx, fy, r]) => ({
        x: Math.min(Math.max(vw / 2 + fx * vw, halfW), vw - halfW),
        y: Math.min(Math.max(vh / 2 + fy * vh, 48), vh - 48),
        r,
        tx: vw / 2,
        ty: vh / 2,
      })),
    );
  }, []);

  // Run the timeline once the start positions exist.
  useEffect(() => {
    if (!slips || phase !== "hidden") return;
    const start = window.requestAnimationFrame(() => {
      timers.current = TIMELINE.map(([next, at]) =>
        window.setTimeout(() => {
          if (next === "gather") aimSlipsAtRows(cardRef.current, setSlips);
          if (next === "done") markIntroSeen();
          setPhase(next);
        }, at),
      );
    });
    return () => window.cancelAnimationFrame(start);
  }, [slips, phase]);

  useEffect(() => () => timers.current.forEach(window.clearTimeout), []);

  // While the intro plays: no scrolling, Escape skips, and a resize ends it cleanly.
  const playing = phase !== "done" && phase !== "settle";
  useEffect(() => {
    if (!playing || !slips) return;
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const onKey = (event: KeyboardEvent) => event.key === "Escape" && finish();
    window.addEventListener("keydown", onKey);
    window.addEventListener("resize", finish);
    return () => {
      document.body.style.overflow = previous;
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("resize", finish);
    };
  }, [playing, slips, finish]);

  const signedIn = ready && !!session;

  return (
    <div
      data-phase={phase}
      className={cn(styles.root, "font-humane bg-mist text-ink-soft min-h-dvh")}
      style={{ "--dx": `${offset.dx}px`, "--dy": `${offset.dy}px` } as React.CSSProperties}
    >
      <header className={cn(styles.reveal, "site-bar")}>
        <div className="mx-auto flex max-w-6xl items-center justify-between px-5 py-4 sm:px-8">
          <Link href="/" className="focus-visible:ring-primary/40 flex items-center gap-2.5 rounded-lg outline-none focus-visible:ring-[3px]">
            <BrandMark />
            <span className="text-[1.0625rem] font-medium">Collections Copilot</span>
          </Link>
          <Link
            href={signedIn ? "/overview" : "/login"}
            className="text-primary hover:bg-seaglass/60 focus-visible:ring-primary/40 rounded-full px-4 py-2 text-[0.9375rem] font-medium outline-none focus-visible:ring-[3px]"
          >
            {signedIn ? "Open workspace" : "Sign in"}
          </Link>
        </div>
      </header>

      <main>
        <section className="mx-auto grid max-w-6xl items-center gap-12 px-5 pt-6 pb-16 sm:px-8 lg:grid-cols-[1.1fr_1fr] lg:gap-16 lg:pt-12 lg:pb-24">
          <div className="max-w-xl">
            <h1
              className={cn(styles.reveal, "text-[2.5rem] leading-[1.06] font-normal tracking-[-0.025em] sm:text-[3.25rem] lg:text-[3.75rem]")}
              style={{ "--d": "120ms" } as React.CSSProperties}
            >
              See the whole customer before you make the call.
            </h1>
            <p
              className={cn(styles.reveal, "text-slate mt-6 max-w-[34rem] text-[1.0625rem] leading-[1.65] sm:text-lg")}
              style={{ "--d": "260ms" } as React.CSSProperties}
            >
              Collections Copilot links each customer&apos;s accounts, cards, loans, notes and cases into one view. It
              suggests a next step that respects contact rules, and every draft waits for a supervisor before it goes
              anywhere.
            </p>
            <div className={cn(styles.reveal, "mt-9 flex flex-wrap items-center gap-x-6 gap-y-3")} style={{ "--d": "400ms" } as React.CSSProperties}>
              <Link
                href={signedIn ? "/overview" : "/login"}
                className="bg-primary text-primary-foreground hover:bg-primary/90 focus-visible:ring-primary/35 inline-flex h-12 items-center rounded-full px-7 text-base font-medium outline-none focus-visible:ring-4"
              >
                {signedIn ? "Open workspace" : "Sign in"}
              </Link>
              <p className="text-slate text-sm">Runs on this computer with synthetic data.</p>
            </div>
          </div>

          <div className="flex justify-center lg:justify-end">
            <CustomerCard ref={cardRef} />
          </div>
        </section>

        <section
          aria-labelledby="roles-heading"
          className={cn(styles.reveal, "border-line-soft border-t")}
          style={{ "--d": "560ms" } as React.CSSProperties}
        >
          <div className="mx-auto max-w-6xl px-5 py-14 sm:px-8">
            <h2 id="roles-heading" className="text-[1.375rem] font-medium tracking-[-0.01em]">
              Sign in with the role that matches your work
            </h2>
            <ul className="mt-6 grid gap-3 md:grid-cols-3">
              {ROLES.map(({ role, title, text, icon: Icon }) => (
                <li key={role}>
                  <Link
                    href={`/login?role=${role}`}
                    className="group bg-paper/70 hover:bg-paper hover:border-seaglass-deep focus-visible:ring-primary/35 border-line-soft flex h-full gap-4 rounded-2xl border p-5 outline-none focus-visible:ring-[3px]"
                  >
                    <Icon className="text-primary mt-0.5 size-5 shrink-0" aria-hidden />
                    <span>
                      <span className="block font-medium">{title}</span>
                      <span className="text-slate mt-1 block text-[0.9375rem] leading-relaxed">{text}</span>
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        </section>
      </main>

      <div className={styles.reveal} style={{ "--d": "620ms" } as React.CSSProperties}>
        <SiteFooter
          links={[
            signedIn ? { href: "/overview", label: "Open workspace" } : { href: "/login", label: "Sign in" },
            { href: "/#roles-heading", label: "What each role can do" },
          ]}
        />
      </div>

      {slips && phase !== "done" && (
        <>
          <div className={styles.slips} aria-hidden>
            {SOURCES.map(({ id, system, fact }, i) => {
              const s = slips[i];
              return (
                <div
                  key={id}
                  className={cn(styles.slip, "bg-paper border-line-soft rounded-xl border px-3.5 py-2.5 shadow-[0_10px_30px_-18px_rgb(31_45_61/0.35)]")}
                  style={
                    {
                      "--x": `${s.x}px`,
                      "--y": `${s.y}px`,
                      "--tx": `${s.tx}px`,
                      "--ty": `${s.ty}px`,
                      "--r": `${s.r}deg`,
                      "--i": i,
                    } as React.CSSProperties
                  }
                >
                  <p className="text-slate text-xs">{system}</p>
                  <p className="text-ink-soft text-sm leading-snug">{fact}</p>
                </div>
              );
            })}
          </div>
          <button
            type="button"
            onClick={finish}
            className={cn(
              styles.skip,
              "text-slate hover:text-ink-soft hover:bg-paper focus-visible:ring-primary/35 fixed right-5 bottom-5 z-40 rounded-full px-4 py-2 text-sm outline-none focus-visible:ring-[3px]",
            )}
          >
            Skip intro
          </button>
        </>
      )}
    </div>
  );
}

/** Point each slip at the row it fills, measured on the centred card. */
function aimSlipsAtRows(card: HTMLElement | null, setSlips: React.Dispatch<React.SetStateAction<Slip[] | null>>) {
  if (!card) return;
  setSlips((current) =>
    current?.map((slip, i) => {
      const row = card.querySelector<HTMLElement>(`[data-source="${SOURCES[i].id}"]`);
      if (!row) return slip;
      const r = row.getBoundingClientRect();
      return { ...slip, tx: r.left + r.width / 2, ty: r.top + r.height / 2 };
    }) ?? null,
  );
}
