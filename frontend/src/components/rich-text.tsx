import { Fragment, type ReactNode } from "react";
import { cn } from "@/lib/utils";

/**
 * Renders the small Markdown subset used by the source policy documents
 * (headings, **bold**, `code`, - and 1. lists) without a parser dependency.
 * Text without Markdown keeps its line breaks, so metric rows and transcript
 * lines display exactly as returned. React escapes all text; no raw HTML.
 */

type Block =
  | { kind: "heading"; level: number; text: string }
  | { kind: "list"; ordered: boolean; start: number; items: string[][] }
  | { kind: "paragraph"; lines: string[] };

const HEADING = /^\s*(#{1,6})\s+(.*)$/;
const LIST_ITEM = /^\s*(?:([-*+])|(\d+)[.)])\s+(.*)$/;
const MARKDOWN = /^\s*#{1,6}\s|\*\*[^*\n]+\*\*/m;

function parse(text: string): Block[] {
  const blocks: Block[] = [];
  let current: Block | null = null;
  const close = () => {
    if (current) blocks.push(current);
    current = null;
  };
  for (const line of text.replace(/\r\n/g, "\n").split("\n")) {
    if (!line.trim()) {
      close();
      continue;
    }
    const heading = HEADING.exec(line);
    if (heading) {
      close();
      blocks.push({ kind: "heading", level: heading[1].length, text: heading[2] });
      continue;
    }
    const item = LIST_ITEM.exec(line);
    if (item) {
      const ordered = !item[1];
      if (current?.kind !== "list" || current.ordered !== ordered) {
        close();
        current = { kind: "list", ordered, start: ordered ? Number(item[2]) : 1, items: [] };
      }
      current.items.push([item[3]]);
      continue;
    }
    // An indented line directly after a list item continues that item.
    if (current?.kind === "list" && /^\s/.test(line)) {
      current.items[current.items.length - 1].push(line.trim());
      continue;
    }
    if (current?.kind !== "paragraph") {
      close();
      current = { kind: "paragraph", lines: [] };
    }
    current.lines.push(line.trim());
  }
  close();
  return blocks;
}

function inline(text: string): ReactNode[] {
  return text.split(/(\*\*[^*\n]+?\*\*|`[^`\n]+`)/g).map((part, i) => {
    if (part.length > 4 && part.startsWith("**") && part.endsWith("**")) {
      return (
        <strong key={i} className="font-semibold">
          {part.slice(2, -2)}
        </strong>
      );
    }
    if (part.length > 2 && part.startsWith("`") && part.endsWith("`")) {
      return (
        <code key={i} className="bg-muted rounded px-1 py-0.5 font-mono text-[0.85em]">
          {part.slice(1, -1)}
        </code>
      );
    }
    return <Fragment key={i}>{part}</Fragment>;
  });
}

/** Markdown wraps lines mid-sentence, so join them; plain text keeps its breaks. */
function lines(parts: string[], markdown: boolean): ReactNode {
  if (markdown) return inline(parts.join(" "));
  return parts.map((part, i) => (
    <Fragment key={i}>
      {i > 0 && <br />}
      {inline(part)}
    </Fragment>
  ));
}

export function RichText({ text, className }: { text: string; className?: string }) {
  const markdown = MARKDOWN.test(text);
  return (
    <div className={cn("space-y-3 break-words", className)}>
      {parse(text).map((block, i) => {
        if (block.kind === "heading") {
          return (
            <h4 key={i} className={cn("font-semibold", block.level <= 2 ? "text-[1.05em]" : "text-[1em]")}>
              {inline(block.text)}
            </h4>
          );
        }
        if (block.kind === "list") {
          const List = block.ordered ? "ol" : "ul";
          return (
            <List
              key={i}
              start={block.ordered && block.start !== 1 ? block.start : undefined}
              className={cn("space-y-1 pl-5", block.ordered ? "list-decimal" : "list-disc")}
            >
              {block.items.map((item, j) => (
                <li key={j}>{lines(item, markdown)}</li>
              ))}
            </List>
          );
        }
        return <p key={i}>{lines(block.lines, markdown)}</p>;
      })}
    </div>
  );
}
