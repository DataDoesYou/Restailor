"use client";
import React from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

// Local remark plugin to convert single newlines to <br> (Streamlit-like nl2br)
function remarkBreaksLocal() {
  return (tree: any) => {
    const SKIP_PARENTS = new Set([
      "code",
      "inlineCode",
      "link",
      "image",
      "imageReference",
      "definition",
    ]);
    const BLOCK_PARENTS = new Set([
      "paragraph",
      "heading",
      "listItem",
      "tableCell",
      "blockquote",
    ]);
    const visit = (node: any, parent: any | null) => {
      if (!node) return;
      if (node.type === "text" && typeof node.value === "string" && parent && !SKIP_PARENTS.has(parent.type)) {
        if (node.value.includes("\n")) {
          const parts = node.value.split("\n");
          const replacement: any[] = [];
          // Only consider trailing-empty suppression if this text node is the last child
          // of a BLOCK-LEVEL parent (true end-of-block), not inside inline wrappers.
          const siblings = parent.children as any[];
          const selfIndex = siblings.indexOf(node);
          const isBlockParent = BLOCK_PARENTS.has(parent.type);
          const isLastInBlock = isBlockParent && selfIndex === siblings.length - 1;
          let trailingEmptyCount = 0;
          if (isLastInBlock) {
            for (let j = parts.length - 1; j >= 0; j--) {
              if (parts[j] === "") trailingEmptyCount++; else break;
            }
          }
          for (let i = 0; i < parts.length; i++) {
            const part = parts[i];
            if (part) replacement.push({ type: "text", value: part });
            const isBoundary = i < parts.length - 1;
            const isInTrailingRun = isLastInBlock && trailingEmptyCount > 0 && i >= parts.length - 1 - trailingEmptyCount;
            // Avoid inserting any <br> for boundaries that fall into the trailing empty run
            if (isBoundary && !isInTrailingRun) replacement.push({ type: "break" });
          }
          if (selfIndex !== -1) siblings.splice(selfIndex, 1, ...replacement);
          return; // replaced this node; do not descend
        }
      }
      if (Array.isArray((node as any).children)) {
        // children may mutate as we splice, so use while loop
        let i = 0;
        while (i < (node as any).children.length) {
          visit((node as any).children[i], node);
          i++;
        }
      }
    };
    visit(tree, null);
  };
}

export type MarkdownProps = {
  children: string;
  className?: string;
};

export default function Markdown({ children, className }: MarkdownProps) {
  // Normalize triple-backtick blocks that might be unclosed; light sanitation
  let src = String(children || "").replace(/\r\n/g, "\n");
  // Minimal defensive sanitation (ReactMarkdown already escapes raw HTML by default unless allowed):
  // Strip script/style tags and inline event handlers to reduce accidental unsafe output if future config changes.
  try {
    src = src
      .replace(/<\/(?:script|style)>/gi, "")
      .replace(/<(script|style)[^>]*?>[\s\S]*?<\/\1>/gi, "")
      .replace(/ on[a-z]+="[^"]*"/gi, "")
      .replace(/ on[a-z]+='[^']*'/gi, "");
  } catch {}
  return (
  <div
    className={[
      "prose prose-invert prose-slate max-w-none leading-relaxed",
  "[&>*:first-child]:mt-0 [&>*:first-child]:pt-0",
      // Local override: match input text color (slate-200 / #e2e8f0) for body text only
      "[--tw-prose-invert-body:theme(colors.slate.200)]",
      "rt-markdown",
      className,
    ].filter(Boolean).join(" ")}
  > 
  <ReactMarkdown
    remarkPlugins={[remarkGfm, remarkBreaksLocal]}
        components={{
    a: (props: any) => <span {...props} />, // disable links for parity/safety
      img: () => null, // ignore images
    hr: (props: any) => (
      <hr
        {...props}
        style={{ border: "none", borderTop: "1px solid #94a3b8", margin: "12px 0", height: 0 }}
      />
    ),
  h1: (props: any) => <h2 {...props} className="text-lg font-semibold mt-3 mb-2" />,
  h2: (props: any) => <h3 {...props} className="text-base font-semibold mt-3 mb-2" />,
  p: (props: any) => <p {...props} className="my-3" />,
  ul: (props: any) => <ul {...props} className="my-3 list-disc pl-6 space-y-1" />,
  ol: (props: any) => <ol {...props} className="my-3 list-decimal pl-6 space-y-1" />,
  li: (props: any) => <li {...props} className="marker:text-slate-400" />,
  blockquote: (props: any) => <blockquote {...props} className="my-3 border-l-4 border-slate-700 pl-3 italic text-slate-300" />,
  table: (props: any) => (
    <div className="overflow-x-auto my-3">
      <table {...props} className="w-full text-sm border-collapse" />
    </div>
  ),
  thead: (props: any) => <thead {...props} className="bg-slate-900/40" />,
  th: (props: any) => <th {...props} className="border border-slate-700 px-2 py-1 text-left font-semibold break-words" />,
  td: (props: any) => <td {...props} className="border border-slate-800 px-2 py-1 align-top break-words" />,
    pre: (props: any) => (
      <div className="overflow-x-auto my-3">
        <pre {...props} className="rounded bg-slate-900/60 p-3 border border-slate-800 w-max min-w-full" />
      </div>
    ),
    code: (props: any) => <code {...props} className="bg-slate-900/60 rounded px-1" />,
        }}
      >
        {src}
      </ReactMarkdown>
      <style jsx>{`
        /* Hide only trailing <br> so UI doesn't show an extra blank line,
           while keeping internal <br> for Word paste fidelity. */
        .rt-markdown p > br:last-child,
  .rt-markdown h1 > br:last-child,
  .rt-markdown h2 > br:last-child,
  .rt-markdown h3 > br:last-child,
  .rt-markdown h4 > br:last-child,
  .rt-markdown h5 > br:last-child,
  .rt-markdown h6 > br:last-child,
        .rt-markdown li > br:last-child,
        .rt-markdown li p > br:last-child,
        .rt-markdown blockquote p > br:last-child,
        .rt-markdown td > br:last-child {
          display: none;
        }
      `}</style>
    </div>
  );
}
