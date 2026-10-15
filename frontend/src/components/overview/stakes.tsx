"use client";

import { useEffect, useRef, useState } from "react";
import { cn, formatCount } from "@/lib/utils";
import { Definition } from "./definition";
import styles from "./overview.module.css";

export interface ValueItem {
  id: string;
  title: string;
  definition: string;
  sql: string;
  value: number;
  secondary: number | null;
  tertiary: number | null;
}

export const money = new Intl.NumberFormat("en-CA", { style: "currency", currency: "CAD", notation: "compact", maximumFractionDigits: 1 });

/** One plain sentence under each figure, built only from the measured values. */
function detail(item: ValueItem) {
  if (item.id === "write_off_exposure")
    return `Overdue on these cases today: ${money.format(item.tertiary ?? 0)}. The source's own expected-loss estimate is ${money.format(item.secondary ?? 0)}.`;
  if (item.id === "hardship_overdue") return `Owed by ${formatCount(item.tertiary)} customers in hardship who have no plan yet.`;
  return `Spent on ${formatCount(item.secondary)} outbound calls and reminders.`;
}

/**
 * Scrollytelling: on wide screens the figure stays pinned on the left and
 * changes as each explanation on the right reaches the middle of the screen.
 */
export function Stakes({ items }: { items: ValueItem[] }) {
  const [active, setActive] = useState(0);
  const steps = useRef<(HTMLLIElement | null)[]>([]);

  // The active step is the last one whose top has passed the middle of the
  // screen. Reading positions on scroll (not waiting for a crossing) keeps the
  // figure right after jumps such as End, a scrollbar drag or a fast fling.
  useEffect(() => {
    let frame = 0;
    const update = () => {
      frame = 0;
      const middle = window.innerHeight / 2;
      let next = 0;
      steps.current.forEach((node, i) => {
        if (node && node.getBoundingClientRect().top <= middle) next = i;
      });
      setActive(next);
    };
    const schedule = () => {
      if (!frame) frame = window.requestAnimationFrame(update);
    };
    update();
    window.addEventListener("scroll", schedule, { passive: true });
    window.addEventListener("resize", schedule);
    return () => {
      window.cancelAnimationFrame(frame);
      window.removeEventListener("scroll", schedule);
      window.removeEventListener("resize", schedule);
    };
  }, [items.length]);

  return (
    <section aria-labelledby="value-heading" className="grid gap-8 lg:grid-cols-[1fr_1fr] lg:gap-16">
      <div className="lg:sticky lg:top-28 lg:self-start">
        <h2 id="value-heading" className="text-[1.75rem] leading-tight font-normal tracking-[-0.015em]">
          What&apos;s at stake
        </h2>
        <p className="text-muted-foreground mt-3 max-w-md leading-relaxed">
          The money behind the problems above, measured from the data. Source estimates are called estimates.
        </p>

        {/* Pinned figure, wide screens only. */}
        <div className="mt-8 hidden lg:grid" aria-hidden>
          {items.map((item, i) => (
            <div key={item.id} data-active={i === active} className={styles.figure}>
              <p className="text-primary text-[5.5rem] leading-none tracking-[-0.035em] tabular-nums">{money.format(item.value)}</p>
              <p className="mt-4 max-w-sm text-lg leading-snug">{item.title}</p>
            </div>
          ))}
        </div>
        <div className="mt-6 hidden gap-1.5 lg:flex" aria-hidden>
          {items.map((item, i) => (
            <span key={item.id} className={cn(styles.tick, "h-1.5 rounded-full", i === active ? "bg-primary w-8" : "bg-seaglass w-4")} />
          ))}
        </div>
      </div>

      <ol>
        {items.map((item, i) => (
          <li
            key={item.id}
            ref={(node) => {
              steps.current[i] = node;
            }}
            data-index={i}
            data-active={i === active}
            className={cn(styles.step, "border-line-soft flex flex-col justify-center border-t py-8 lg:min-h-[38vh] lg:py-10 lg:first:border-t-0")}
          >
            <p className="text-primary text-[3rem] leading-none tracking-[-0.03em] tabular-nums lg:hidden">{money.format(item.value)}</p>
            <h3 className="mt-3 text-[1.25rem] leading-snug font-medium lg:mt-0">{item.title}</h3>
            <p className="text-muted-foreground mt-2 max-w-md leading-relaxed">{detail(item)}</p>
            <Definition definition={item.definition} sql={item.sql} />
          </li>
        ))}
      </ol>
    </section>
  );
}
