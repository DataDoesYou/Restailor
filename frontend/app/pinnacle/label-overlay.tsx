"use client";
import { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";

type NodeInfo = { id: string; label: string; rect: DOMRect; el: HTMLElement };

export function LabelOverlay({ enabled }: { enabled?: boolean }) {
  const [nodes, setNodes] = useState<NodeInfo[]>([]);
  const root = useRef<HTMLElement | null>(null);
  const ro = useRef<ResizeObserver | null>(null);

  useEffect(() => {
    if (!enabled) {
      setNodes([]);
      ro.current?.disconnect();
      ro.current = null;
      return;
    }

    const source = Array.from(document.querySelectorAll<HTMLElement>("[data-label]"));
    const get = () =>
      source.map((el) => ({
        id: el.getAttribute("data-testid") || el.id || Math.random().toString(36).slice(2),
        label: el.getAttribute("data-label") || "",
        rect: el.getBoundingClientRect(),
        el,
      }));
    setNodes(get());

    const obs = new ResizeObserver(() => setNodes(get()));
    ro.current = obs;
    source.forEach((el) => obs.observe(el));

    const onScroll = () => setNodes(get());
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll);
    return () => {
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onScroll);
      obs.disconnect();
    };
  }, [enabled]);

  const container = useMemo(() => {
    if (typeof document === "undefined") return null;
    let c = document.getElementById("__pinnacle_overlay__") as HTMLDivElement | null;
    if (!c) {
      c = document.createElement("div");
      c.id = "__pinnacle_overlay__";
      c.style.position = "fixed";
      c.style.inset = "0";
      c.style.pointerEvents = "none";
      c.style.zIndex = "9999";
      document.body.appendChild(c);
    }
    return c;
  }, []);

  if (!enabled || !container) return null;

  return createPortal(
    <div aria-hidden>
      {nodes.map((n) => (
        <button
          key={n.id}
          className="p-label"
          style={{
            position: "absolute",
            // Overlay is fixed to the viewport; use viewport coords directly
            left: Math.max(8, n.rect.left),
            top: Math.max(8, n.rect.top - 18),
          }}
          onClick={(e) => {
            e.preventDefault();
            n.el.scrollIntoView({ behavior: "smooth", block: "center" });
            setTimeout(() => n.el.focus?.(), 250);
          }}
        >
          {n.label}
        </button>
      ))}
    </div>,
    container
  );
}

export default LabelOverlay;
