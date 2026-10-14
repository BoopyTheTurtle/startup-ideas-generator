"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Suspense } from "react";

const LINKS = [
  { href: "/", label: "Radar" },
  { href: "/merges", label: "Merges" },
  { href: "/runs", label: "Runs" },
  { href: "/label", label: "Label" },
];

function isCurrent(href: string, path: string | null): boolean {
  if (path === null) return false;
  if (href === "/") return path === "/" || path.startsWith("/themes") || path.startsWith("/problems");
  return path.startsWith(href);
}

function NavList({ path }: { path: string | null }) {
  return (
    <ul className="flex flex-wrap gap-1 text-sm">
      {LINKS.map((l) => {
        const current = isCurrent(l.href, path);
        return (
          <li key={l.href}>
            <Link
              href={l.href}
              aria-current={current ? "page" : undefined}
              className={`block rounded px-3 py-1.5 ${
                current
                  ? "bg-zinc-900 text-white dark:bg-zinc-100 dark:text-zinc-900"
                  : "hover:bg-zinc-100 dark:hover:bg-zinc-800"
              }`}
            >
              {l.label}
            </Link>
          </li>
        );
      })}
    </ul>
  );
}

function CurrentNav() {
  return <NavList path={usePathname()} />;
}

// The pathname is runtime data under Cache Components, so the highlighted list streams in
// behind a plain one that ships in the static shell.
export function NavLinks() {
  return (
    <Suspense fallback={<NavList path={null} />}>
      <CurrentNav />
    </Suspense>
  );
}
