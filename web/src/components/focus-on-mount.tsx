"use client";

import { useEffect, useRef, type ReactNode } from "react";

// A banner that takes focus when it appears, so a screen reader announces the outcome of
// an action that navigated (the form that started it is gone). tabIndex -1: focusable
// by script only, never a tab stop.
export function FocusOnMount({ className, children }: { className?: string; children: ReactNode }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    ref.current?.focus();
  }, []);
  return (
    <div ref={ref} tabIndex={-1} role="status" className={className}>
      {children}
    </div>
  );
}
