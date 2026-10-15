"use client";

import { useEffect, useRef, useState } from "react";
import Lenis from "lenis";

/** True once the element has scrolled into view (and stays true). */
export function useInView<T extends Element>(options: IntersectionObserverInit = { threshold: 0.15, rootMargin: "0px 0px -8% 0px" }) {
  const ref = useRef<T>(null);
  const [inView, setInView] = useState(false);
  const { threshold, rootMargin } = options;
  useEffect(() => {
    const node = ref.current;
    if (!node || inView) return;
    if (typeof IntersectionObserver === "undefined") {
      setInView(true);
      return;
    }
    const observer = new IntersectionObserver(([entry]) => {
      if (entry.isIntersecting) {
        setInView(true);
        observer.disconnect();
      }
    }, { threshold, rootMargin });
    observer.observe(node);
    return () => observer.disconnect();
  }, [inView, threshold, rootMargin]);
  return [ref, inView] as const;
}

/** Content that sharpens from a soft blur as it scrolls into view. */
export function Reveal({
  delay = 0,
  style,
  children,
  ...rest
}: { delay?: number } & React.ComponentProps<"div">) {
  const [ref, inView] = useInView<HTMLDivElement>();
  return (
    <div
      ref={ref}
      {...rest}
      data-reveal={inView ? "shown" : "hidden"}
      style={{ ...style, "--reveal-delay": `${delay}ms` } as React.CSSProperties}
    >
      {children}
    </div>
  );
}

const reducedMotion = () => window.matchMedia("(prefers-reduced-motion: reduce)").matches;

/**
 * Inertial smooth scrolling while mounted; off with reduced motion. Nested
 * scroll areas (a sticky plan panel, a wide table) keep scrolling natively.
 */
export function useSmoothScroll() {
  useEffect(() => {
    if (reducedMotion()) return;
    const lenis = new Lenis({ autoRaf: true, lerp: 0.12, anchors: true, allowNestedScroll: true });
    return () => lenis.destroy();
  }, []);
}

// What reveals on its own: cards, alerts, rows of tables that are not inside a
// card, and anything marked data-auto-reveal. Nested matches ride with the parent.
const AUTO_REVEAL = '[data-slot="card"], [data-slot="alert"], tbody > tr, [data-auto-reveal]';
const FRESH_MS = 1500;

/**
 * Gives every page the same entrance: content blurs into focus as it first
 * appears or scrolls into view. Content that appears later in response to an
 * action (a plan step updating, an answer arriving) shows immediately instead,
 * so the motion never gets in the way of work.
 */
export function useAutoReveal(root: React.RefObject<HTMLElement | null>, routeKey: string) {
  useEffect(() => {
    const container = root.current;
    if (!container || reducedMotion() || typeof IntersectionObserver === "undefined") return;
    const start = performance.now();

    const observer = new IntersectionObserver(
      (entries) => {
        let order = 0;
        for (const entry of entries) {
          if (!entry.isIntersecting) continue;
          const el = entry.target as HTMLElement;
          el.style.setProperty("--reveal-delay", `${Math.min(order++, 8) * 60}ms`);
          el.dataset.reveal = "shown";
          observer.unobserve(el);
        }
      },
      { threshold: 0.06, rootMargin: "0px 0px -6% 0px" },
    );

    const consider = (el: HTMLElement) => {
      if (el.dataset.reveal || el.parentElement?.closest("[data-reveal], [data-no-reveal]")) return;
      const box = el.getBoundingClientRect();
      const onScreen = box.top < window.innerHeight && box.bottom > 0;
      if (onScreen && performance.now() - start > FRESH_MS) return;
      el.dataset.reveal = "hidden";
      observer.observe(el);
    };
    const scan = (node: Node) => {
      if (!(node instanceof HTMLElement)) return;
      if (node.matches(AUTO_REVEAL)) consider(node);
      node.querySelectorAll<HTMLElement>(AUTO_REVEAL).forEach(consider);
    };

    scan(container);
    const mutations = new MutationObserver((records) => records.forEach((r) => r.addedNodes.forEach(scan)));
    mutations.observe(container, { childList: true, subtree: true });
    return () => {
      mutations.disconnect();
      observer.disconnect();
      // Never leave anything stuck invisible when the route changes mid-reveal.
      container.querySelectorAll<HTMLElement>('[data-reveal="hidden"]').forEach((el) => (el.dataset.reveal = "shown"));
    };
  }, [root, routeKey]);
}
