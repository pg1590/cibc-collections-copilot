import { cn } from "@/lib/utils";

// Six source systems (CRM, core banking, cards, lending, bureau, collections)
// linked to one customer: the same idea the welcome animation plays out.
const POINTS = Array.from({ length: 6 }, (_, i) => {
  const angle = (Math.PI / 3) * i - Math.PI / 2;
  return { x: 16 + 11 * Math.cos(angle), y: 16 + 11 * Math.sin(angle) };
});

const TONES = {
  light: { line: "var(--seaglass-deep)", point: "var(--paper)", ring: "var(--primary)", core: "var(--primary)" },
  dark: { line: "#3f7f78", point: "var(--chrome)", ring: "var(--chrome-accent)", core: "var(--chrome-accent)" },
};

export function BrandMark({ className, tone = "light" }: { className?: string; tone?: keyof typeof TONES }) {
  const c = TONES[tone];
  return (
    <svg viewBox="0 0 32 32" aria-hidden className={cn("size-7 shrink-0", className)}>
      {POINTS.map(({ x, y }, i) => (
        <line key={`l${i}`} x1={x} y1={y} x2={16} y2={16} stroke={c.line} strokeWidth={1.25} />
      ))}
      {POINTS.map(({ x, y }, i) => (
        <circle key={`p${i}`} cx={x} cy={y} r={2.1} fill={c.point} stroke={c.ring} strokeWidth={1.25} />
      ))}
      <circle cx={16} cy={16} r={4.2} fill={c.core} />
    </svg>
  );
}
