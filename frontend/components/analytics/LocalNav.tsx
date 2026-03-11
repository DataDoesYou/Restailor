"use client";

import React from "react";

export function LocalNav(props: {
  active: string;
  setActive: (k: string) => void;
  items?: { key: string; label: string }[];
  showActive?: boolean;
}) {
  const showActive = props.showActive !== undefined ? props.showActive : true;
  const items = props.items || [
    { key: "overview", label: "Overview" },
    { key: "usage", label: "Usage" },
    { key: "spend", label: "Spend" },
  { key: "models", label: "Models" },
  // Keep key as 'ledger' for URL/hash/back-compat, but present as 'Deposits'
  { key: "ledger", label: "Deposits" },
  ];
  
  return (
    <>
      {/* Desktop - normal layout */}
      <div className="hidden md:flex items-center gap-2 border-b border-outline-var sticky top-[52px] bg-[#0b0e14] z-10" role="tablist" aria-label="Analytics sections">
        {items.map(it => (
          <button
            key={it.key}
            id={`tab-${it.key}`}
            role="tab"
            aria-selected={showActive ? props.active === it.key : false}
            aria-controls={`panel-${it.key}`}
            onClick={() => props.setActive(it.key)}
            className={
              // All tabs (including Overview) use the same active underline and bold text.
              // Border width is constant (border-b-2) to avoid any height shift.
              // Using !important on bg to override global button styles from globals.css
              "px-3 py-2 text-sm -mb-px border-b-2 text-foreground !bg-transparent hover:!bg-transparent focus:!bg-transparent active:!bg-transparent !shadow-none !transition-none outline-none focus:outline-none focus-visible:outline-none focus:ring-0 focus-visible:ring-0 " +
              (showActive && props.active === it.key
                ? "border-[var(--chart-1)] font-bold"
                : "border-transparent font-normal")
            }
          >{it.label}</button>
        ))}
      </div>
      {/* Mobile - horizontal scrollable tabs */}
      <div className="md:hidden flex items-center gap-2 border-b border-outline-var overflow-x-auto bg-[#0b0e14] z-10 -mx-4 px-4 [&::-webkit-scrollbar]:hidden" style={{ scrollbarWidth: 'none', msOverflowStyle: 'none' }} role="tablist" aria-label="Analytics sections">
        {items.map(it => (
          <button
            key={it.key}
            id={`tab-mobile-${it.key}`}
            role="tab"
            aria-selected={showActive ? props.active === it.key : false}
            aria-controls={`panel-${it.key}`}
            onClick={() => props.setActive(it.key)}
            className={
              "px-4 py-3 text-base -mb-px border-b-2 text-foreground whitespace-nowrap !bg-transparent hover:!bg-transparent focus:!bg-transparent active:!bg-transparent !shadow-none !transition-none outline-none focus:outline-none focus-visible:outline-none focus:ring-0 focus-visible:ring-0 " +
              (showActive && props.active === it.key
                ? "border-[var(--chart-1)] font-bold"
                : "border-transparent font-normal")
            }
          >{it.label}</button>
        ))}
      </div>
    </>
  );
}
