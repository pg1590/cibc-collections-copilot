import { Reveal } from "@/components/motion/reveal";
import type { PortfolioCheck } from "@/lib/plan-types";
import { formatCount } from "@/lib/utils";
import { Definition } from "./definition";

const GROUPS: { severity: string; title: string; dot: string; figure: string; edge: string }[] = [
  { severity: "high", title: "Needs action now", dot: "bg-review", figure: "text-review-foreground", edge: "border-l-review" },
  { severity: "medium", title: "Keep an eye on", dot: "bg-amber", figure: "text-amber-foreground", edge: "border-l-amber" },
];

/** Portfolio policy checks as a calm list, urgent ones first. */
export function Problems({ checks }: { checks: PortfolioCheck[] }) {
  const urgent = checks.filter((c) => c.severity === "high").length;
  return (
    <section aria-labelledby="checks-heading" className="grid gap-6 lg:grid-cols-[17rem_1fr] lg:gap-16">
      <div className="lg:sticky lg:top-28 lg:self-start">
        <h2 id="checks-heading" className="text-[1.75rem] leading-tight font-normal tracking-[-0.015em]">
          Problems across all customers
        </h2>
        <p className="text-muted-foreground mt-3 leading-relaxed">
          {checks.length} policy checks run over every open case.{" "}
          {urgent > 0 ? `${urgent} of them need action now.` : "None needs urgent action."}
        </p>
      </div>

      <div className="space-y-10">
        {GROUPS.map(({ severity, title, dot, figure, edge }) => {
          const rows = checks.filter((c) => c.severity === severity);
          if (rows.length === 0) return null;
          return (
            <div key={severity}>
              <h3 className="text-foreground mb-3 flex items-center gap-2 text-[0.9375rem] font-medium">
                <span className={`${dot} size-2 rounded-full`} aria-hidden />
                {title}
              </h3>
              <ul>
                {rows.map((check, i) => (
                  <li key={check.id}>
                    <Reveal
                      delay={i * 70}
                      className={`bg-card ${edge} mb-3 grid gap-x-8 gap-y-2 rounded-2xl border border-l-4 px-5 py-5 shadow-[0_1px_2px_rgb(31_45_61/0.04)] sm:grid-cols-[9rem_1fr]`}
                    >
                      <p className="tabular-nums">
                        <span className={`${figure} block text-[2.125rem] leading-none tracking-[-0.02em]`}>{formatCount(check.value)}</span>
                        <span className="text-muted-foreground mt-1 block text-sm">{check.unit}</span>
                      </p>
                      <div>
                        <p className="text-[1.0625rem] leading-snug font-medium">{check.title}</p>
                        <p className="text-muted-foreground mt-1 leading-relaxed">{check.action}</p>
                        <Definition definition={check.definition} sql={check.sql} source={check.policy} />
                      </div>
                    </Reveal>
                  </li>
                ))}
              </ul>
            </div>
          );
        })}
      </div>
    </section>
  );
}
