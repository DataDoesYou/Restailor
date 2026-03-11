"use client";
import { useState } from "react";
import MobileDrawer from "@/components/chrome/MobileDrawer";

interface LayoutWrapperProps {
  children: React.ReactNode;
  sidebarContent: React.ReactNode;
}

export default function LayoutWrapper({ children, sidebarContent }: LayoutWrapperProps) {
  const [isDrawerOpen, setIsDrawerOpen] = useState(false);

  return (
    <>
      {/* Mobile hamburger button */}
      <div className="fixed top-4 right-4 z-30 md:hidden">
        <button
          onClick={() => setIsDrawerOpen(true)}
          className="p-1.5 rounded-md bg-slate-800/90 hover:bg-slate-700 text-slate-200 shadow-lg transition-colors backdrop-blur-sm"
          aria-expanded={isDrawerOpen}
          aria-controls="mobile-sidebar"
          aria-label="Open navigation menu"
        >
          <svg
            className="w-5 h-5"
            fill="none"
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth="2"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path d="M4 6h16M4 12h16M4 18h16" />
          </svg>
        </button>
      </div>

      {/* Mobile drawer */}
      <MobileDrawer isOpen={isDrawerOpen} onClose={() => setIsDrawerOpen(false)}>
        <div id="mobile-sidebar">
          {sidebarContent}
        </div>
      </MobileDrawer>

      {/* Main layout container */}
      <div className="w-full h-screen px-4 py-4 md:px-0 md:py-0 md:grid md:grid-cols-[240px_1fr] md:gap-0 flex flex-col gap-4">
        {/* Desktop sidebar - hidden on mobile */}
        <div className="hidden md:block md:w-[240px] md:min-w-[240px] md:max-w-[240px] md:shrink-0 md:h-screen md:overflow-y-auto">
          {sidebarContent}
        </div>

        {/* Main content area */}
        <div className="min-w-0 md:w-full md:h-screen md:overflow-y-auto md:px-6 md:pt-6 md:pb-6">
          {children}
        </div>
      </div>
    </>
  );
}
