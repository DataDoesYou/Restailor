"use client";
import { useState } from "react";

interface DisclosureProps {
  title: string;
  children: React.ReactNode;
  defaultOpen?: boolean;
  className?: string;
}

export default function Disclosure({ title, children, defaultOpen = false, className = "" }: DisclosureProps) {
  const [isOpen, setIsOpen] = useState(defaultOpen);

  return (
    <div className={className}>
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center justify-between w-full text-left p-3 rounded-lg bg-slate-800/50 hover:bg-slate-800 transition-colors"
        aria-expanded={isOpen}
        aria-controls={`disclosure-content-${title.replace(/\s/g, '-')}`}
      >
        <span className="font-medium text-slate-200">{title}</span>
        <svg
          className={`w-5 h-5 text-slate-400 transition-transform ${isOpen ? 'rotate-180' : ''}`}
          fill="none"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="2"
          viewBox="0 0 24 24"
          stroke="currentColor"
          aria-hidden="true"
        >
          <path d="M19 9l-7 7-7-7" />
        </svg>
      </button>
      {isOpen && (
        <div
          id={`disclosure-content-${title.replace(/\s/g, '-')}`}
          className="mt-3 text-slate-300"
        >
          {children}
        </div>
      )}
    </div>
  );
}
