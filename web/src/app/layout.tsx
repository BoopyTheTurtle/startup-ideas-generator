import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import { NavLinks } from "@/components/nav-links";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: { template: "%s · Startup ideas generator", default: "Startup ideas generator" },
  description: "Problem radar and steering",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col">
        <a
          href="#main"
          className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-2 focus:z-10 focus:rounded focus:bg-white focus:px-3 focus:py-2 focus:text-sm dark:focus:bg-zinc-900"
        >
          Skip to content
        </a>
        <header className="border-b border-zinc-200 dark:border-zinc-800">
          <nav
            aria-label="Main"
            className="mx-auto flex w-full max-w-5xl flex-wrap items-center justify-between gap-2 px-4 py-2"
          >
            <span className="text-sm font-semibold">Startup ideas generator</span>
            <NavLinks />
          </nav>
        </header>
        <div id="main" tabIndex={-1} className="flex-1 outline-none">
          {children}
        </div>
      </body>
    </html>
  );
}
