"use client";

import React from "react";
import { usePathname } from "next/navigation";

type TooltipProps = {
  content: string | null | undefined;
  children: React.ReactNode;
  className?: string;
};

export default function Tooltip({ content, children, className }: TooltipProps) {
  const txt = String(content || "").trim();
  const pathname = usePathname();
  const isRootPage = typeof pathname === "string" && pathname === "/";
  if (!txt || isRootPage) return <>{children}</>;

  // Prefer not to wrap to avoid affecting layout; instead, inject an absolutely
  // positioned tooltip inside the child element and add relative/group classes.
  if (React.isValidElement(children)) {
    const origClass = (children.props as any)?.className || "";
    const mergedClass = `${origClass} relative group ${className || ""}`.trim();
    const tooltipEl = (
      <span
        key="tooltip"
        role="tooltip"
        className="pointer-events-none absolute bottom-full left-1/2 -translate-x-1/2 mb-2 z-50 whitespace-pre text-left w-max max-w-[640px] rounded-md bg-slate-900 text-white text-base leading-snug px-4 py-2 shadow-lg opacity-0 group-hover:opacity-100 transition-opacity duration-100"
      >
        {txt}
      </span>
    );
    const origChildren = (children.props as any)?.children;
    const childArray = Array.isArray(origChildren) ? origChildren : [origChildren];
    return React.cloneElement(children as React.ReactElement<any>, { className: mergedClass }, 
      ...childArray.map((child, idx) => React.isValidElement(child) ? React.cloneElement(child, { key: `child-${idx}` }) : child),
      tooltipEl
    );
  }

  // Fallback: wrap non-element nodes minimally without impacting size
  return (
    <span className={`relative group ${className || ""}`}>
      {children}
      <span
        role="tooltip"
        className="pointer-events-none absolute bottom-full left-1/2 -translate-x-1/2 mb-2 z-50 whitespace-pre text-left w-max max-w-[640px] rounded-md bg-slate-900 text-white text-base leading-snug px-4 py-2 shadow-lg opacity-0 group-hover:opacity-100 transition-opacity duration-100"
      >
        {txt}
      </span>
    </span>
  );
}
