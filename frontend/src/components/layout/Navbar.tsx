"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Briefcase, Eye, Search, BarChart3, BookOpen } from "lucide-react";
import ThemeToggle from "./ThemeToggle";
import clsx from "clsx";

const NAV_LINKS = [
  { href: "/portfolio", label: "Portfolio", icon: Briefcase },
  { href: "/watchlist", label: "Watchlist", icon: Eye },
  { href: "/screener", label: "Screener", icon: Search },
  { href: "/glossary", label: "Glossary", icon: BookOpen },
];

export default function Navbar() {
  const pathname = usePathname();

  return (
    <nav className="fixed top-0 left-0 right-0 z-50 h-14 bg-white dark:bg-slate-900 border-b border-slate-200 dark:border-slate-800 flex items-center px-4 gap-6">
      {/* Logo */}
      <Link
        href="/portfolio"
        className="flex items-center gap-2 text-slate-900 dark:text-slate-100 font-bold text-base shrink-0"
      >
        <BarChart3 size={20} className="text-emerald-500" />
        <span>Invest Solo</span>
      </Link>

      {/* Divider */}
      <div className="w-px h-5 bg-slate-200 dark:bg-slate-700" />

      {/* Nav Links */}
      <div className="flex items-center gap-1">
        {NAV_LINKS.map(({ href, label, icon: Icon }) => {
          const isActive =
            pathname === href || (href !== "/" && pathname.startsWith(href));
          return (
            <Link
              key={href}
              href={href}
              className={clsx(
                "flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm font-medium transition-colors",
                isActive
                  ? "bg-slate-100 dark:bg-slate-800 text-slate-900 dark:text-slate-100"
                  : "text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-100 hover:bg-slate-50 dark:hover:bg-slate-800/60"
              )}
            >
              <Icon size={15} />
              {label}
            </Link>
          );
        })}
      </div>

      {/* Spacer */}
      <div className="flex-1" />

      {/* Theme Toggle */}
      <ThemeToggle />
    </nav>
  );
}
