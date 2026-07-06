'use client';

/**
 * Podcast dashboard shell. Mirrors the Command Center AppShell conventions
 * exactly (design Section 4.4): w-56 desktop sidebar collapsible to w-16,
 * mobile top bar plus bottom nav with safe-area padding, identical active
 * and hover states, identical logo area. The one addition is the "Podcast"
 * nav item (Mic icon, after Departments) and, for operator sessions only,
 * the "Podcast Ops" item; operator entries never render for clients.
 */

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
  Home,
  BarChart3,
  Building2,
  Mic,
  Settings,
  ShieldCheck,
  ChevronLeft,
  ChevronRight,
  Menu,
  X,
} from 'lucide-react';
import { useLogoUrl } from '@/hooks/useLogoUrl';

interface NavItem {
  label: string;
  href: string;
  icon: React.ReactNode;
}

function navItems(isOperator: boolean): NavItem[] {
  const items: NavItem[] = [
    { label: 'Home', href: '/', icon: <Home className="w-5 h-5" /> },
    { label: 'CEO Board', href: '/ceo-board', icon: <BarChart3 className="w-5 h-5" /> },
    { label: 'Departments', href: '/workspace', icon: <Building2 className="w-5 h-5" /> },
    { label: 'Podcast', href: '/podcast', icon: <Mic className="w-5 h-5" /> },
  ];
  if (isOperator) {
    items.push({
      label: 'Podcast Ops',
      href: '/podcast/ops',
      icon: <ShieldCheck className="w-5 h-5" />,
    });
  }
  items.push({ label: 'Settings', href: '/settings', icon: <Settings className="w-5 h-5" /> });
  return items;
}

function isActiveRoute(pathname: string, href: string): boolean {
  if (href === '/') return pathname === '/';
  if (href === '/podcast') {
    return pathname === '/podcast' || (pathname.startsWith('/podcast/') && !pathname.startsWith('/podcast/ops'));
  }
  return pathname.startsWith(href);
}

export default function PodcastShell({
  isOperator,
  children,
}: {
  isOperator: boolean;
  children: React.ReactNode;
}) {
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const pathname = usePathname();
  const logoUrl = useLogoUrl();
  const items = navItems(isOperator);
  // Bottom nav keeps to five entries max, matching the AppShell density.
  const bottomItems = items.slice(0, 5);

  useEffect(() => {
    setMobileOpen(false);
  }, [pathname]);

  useEffect(() => {
    const saved = localStorage.getItem('bcc-sidebar-collapsed');
    if (saved === 'true') setCollapsed(true);
  }, []);

  const toggleCollapsed = () => {
    const next = !collapsed;
    setCollapsed(next);
    localStorage.setItem('bcc-sidebar-collapsed', String(next));
  };

  return (
    <div className="flex min-h-screen">
      <aside
        className={`hidden md:flex flex-col bg-white border-r border-gray-200 transition-[width] duration-200 ease-in-out flex-shrink-0 ${
          collapsed ? 'w-16' : 'w-56'
        }`}
      >
        <div className="h-14 flex items-center px-4 border-b border-gray-100">
          <Link href="/" className="flex items-center gap-2 overflow-hidden">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={logoUrl} alt="Logo" className="h-8 w-8 flex-shrink-0" />
            {!collapsed && (
              <span className="text-sm font-bold text-gray-900 whitespace-nowrap">
                Command Center
              </span>
            )}
          </Link>
        </div>

        <nav className="flex-1 py-3 px-2 space-y-1">
          {items.map((item) => {
            const active = isActiveRoute(pathname, item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                title={collapsed ? item.label : undefined}
                className={`flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors ${
                  active
                    ? 'bg-brand-50 text-brand-700 border-l-[3px] border-brand-500'
                    : 'text-gray-600 hover:bg-gray-50 hover:text-gray-900 border-l-[3px] border-transparent'
                } ${collapsed ? 'justify-center px-0' : ''}`}
              >
                <span className={active ? 'text-brand-600' : 'text-gray-400'}>{item.icon}</span>
                {!collapsed && <span>{item.label}</span>}
              </Link>
            );
          })}
        </nav>

        <div className="p-2 border-t border-gray-100">
          <button
            onClick={toggleCollapsed}
            className="flex items-center justify-center w-full px-3 py-2 rounded-lg text-gray-400 hover:text-gray-600 hover:bg-gray-50 transition-colors"
            title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          >
            {collapsed ? <ChevronRight className="w-4 h-4" /> : <ChevronLeft className="w-4 h-4" />}
          </button>
        </div>
      </aside>

      <div className="flex-1 flex flex-col min-w-0">
        <header className="md:hidden h-14 bg-white border-b border-gray-200 flex items-center justify-between px-4 flex-shrink-0">
          <Link href="/" className="flex items-center gap-2">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={logoUrl} alt="Logo" className="h-8 w-8" />
            <span className="text-sm font-bold text-gray-900">Command Center</span>
          </Link>
          <button
            onClick={() => setMobileOpen(!mobileOpen)}
            className="p-2 rounded-lg text-gray-500 hover:bg-gray-100 transition-colors"
            aria-label={mobileOpen ? 'Close navigation' : 'Open navigation'}
          >
            {mobileOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
          </button>
        </header>

        {mobileOpen && (
          <div className="md:hidden fixed inset-0 z-50">
            <div className="absolute inset-0 bg-black/30" onClick={() => setMobileOpen(false)} />
            <nav className="absolute top-14 left-0 right-0 bg-white border-b border-gray-200 shadow-lg p-3 space-y-1">
              {items.map((item) => {
                const active = isActiveRoute(pathname, item.href);
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    className={`flex items-center gap-3 px-4 py-3 rounded-lg text-sm font-medium transition-colors ${
                      active ? 'bg-brand-50 text-brand-700' : 'text-gray-600 hover:bg-gray-50'
                    }`}
                  >
                    <span className={active ? 'text-brand-600' : 'text-gray-400'}>{item.icon}</span>
                    <span>{item.label}</span>
                  </Link>
                );
              })}
            </nav>
          </div>
        )}

        <main className="flex-1 overflow-auto">{children}</main>

        <nav className="md:hidden fixed bottom-0 left-0 right-0 bg-white border-t border-gray-200 flex items-center justify-around py-2 px-1 z-40 safe-area-bottom">
          {bottomItems.map((item) => {
            const active = isActiveRoute(pathname, item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`flex flex-col items-center gap-0.5 px-2 py-1 rounded-lg text-[10px] font-medium transition-colors min-w-[56px] ${
                  active ? 'text-brand-600' : 'text-gray-400'
                }`}
              >
                <span className={active ? 'text-brand-600' : 'text-gray-400'}>{item.icon}</span>
                <span>{item.label}</span>
              </Link>
            );
          })}
        </nav>
      </div>
    </div>
  );
}
