import Link from "next/link";
import { BrandMark } from "@/components/landing/brand-mark";
import { cn } from "@/lib/utils";

const DATASET_URL = "https://huggingface.co/datasets/nuxsh/maple-collections-hackathon";

/**
 * One footer for every page. The facts here are the ones people should be able
 * to find anywhere without them crowding the header: what the data is, that
 * nothing reaches a real customer, and who built it.
 */
export function SiteFooter({ links, className }: { links: { href: string; label: string }[]; className?: string }) {
  return (
    <footer className={cn("bg-chrome text-chrome-muted", className)}>
      <div className="mx-auto grid max-w-7xl gap-10 px-4 py-12 sm:px-8 md:grid-cols-[1.5fr_1fr_1.2fr]">
        <div className="max-w-sm">
          <Link
            href="/"
            className="text-chrome-foreground inline-flex items-center gap-2.5 rounded-lg outline-none focus-visible:ring-[3px] focus-visible:ring-chrome-accent/60"
          >
            <BrandMark tone="dark" className="size-6" />
            <span className="font-medium">Collections Copilot</span>
          </Link>
          <p className="mt-3 text-[0.9375rem] leading-relaxed">
            One view of each customer, clear answers about the portfolio, and drafts that a person approves before
            anything is sent.
          </p>
        </div>

        <nav aria-label="Footer">
          <p className="text-chrome-foreground text-[0.9375rem] font-medium">Go to</p>
          <ul className="mt-3 grid grid-cols-2 gap-x-8 gap-y-2 text-[0.9375rem]">
            {links.map(({ href, label }) => (
              <li key={href}>
                <Link
                  href={href}
                  className="hover:text-chrome-accent rounded underline-offset-4 outline-none hover:underline focus-visible:ring-[3px] focus-visible:ring-chrome-accent/60"
                >
                  {label}
                </Link>
              </li>
            ))}
          </ul>
        </nav>

        <div>
          <p className="text-chrome-foreground text-[0.9375rem] font-medium">Good to know</p>
          <ul className="mt-3 space-y-2 text-[0.9375rem] leading-relaxed">
            <li>Runs on this computer with synthetic Maple Bank data only.</li>
            <li>Nothing here contacts a real customer.</li>
            <li>Every draft waits for a supervisor&apos;s decision.</li>
          </ul>
        </div>
      </div>

      <div className="bg-chrome-deep">
        <div className="mx-auto flex max-w-7xl flex-col gap-2 px-4 py-5 text-sm sm:flex-row sm:items-center sm:justify-between sm:px-8">
          <p>Built by team Adda Wale for the CIBC Collections Hackathon 2026.</p>
          <p>
            Data:{" "}
            <a
              href={DATASET_URL}
              target="_blank"
              rel="noopener noreferrer"
              className="text-chrome-foreground hover:text-chrome-accent rounded underline underline-offset-4 outline-none focus-visible:ring-[3px] focus-visible:ring-chrome-accent/60"
            >
              Maple Bank synthetic release
            </a>
            , CC BY 4.0
          </p>
        </div>
      </div>
    </footer>
  );
}
