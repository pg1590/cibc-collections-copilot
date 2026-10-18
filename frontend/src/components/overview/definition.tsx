import { ChevronDown } from "lucide-react";
import { PolicyLink } from "@/components/policy-link";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";

/** Every Overview number can be opened to show what it counts and the SQL behind it. */
export function Definition({ definition, sql, source }: { definition: string; sql: string; source?: string }) {
  return (
    <Collapsible className="mt-2">
      <CollapsibleTrigger className="text-muted-foreground hover:text-foreground group inline-flex items-center gap-1 rounded text-sm underline-offset-4 outline-none hover:underline focus-visible:ring-[3px] focus-visible:ring-ring/35">
        <ChevronDown className="size-4 transition-transform group-data-[state=open]:rotate-180" aria-hidden />
        Definition and SQL
      </CollapsibleTrigger>
      <CollapsibleContent className="mt-3 space-y-2.5">
        <p className="text-[0.9375rem] leading-relaxed">{definition}</p>
        {source && (
          <p className="text-muted-foreground flex flex-wrap items-center gap-2 text-sm">
            Policy: <PolicyLink text={source} />
          </p>
        )}
        <pre
          data-lenis-prevent
          className="bg-muted/80 overflow-x-auto rounded-xl p-3 font-mono text-[0.8125rem] leading-relaxed whitespace-pre-wrap"
        >
          {sql}
        </pre>
      </CollapsibleContent>
    </Collapsible>
  );
}
