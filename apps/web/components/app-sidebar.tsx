'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { BarChart3, GitCompareArrows, Sliders, TrendingUp, LogOut } from 'lucide-react'
import { useAuth } from '@/contexts/auth-context'
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuItem,
  SidebarSeparator,
} from '@/components/ui/sidebar'
import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import { cn } from '@/lib/utils'

const navItems = [
  { title: 'Plan',     href: '/plan',     icon: BarChart3,        desc: 'Optimised sequence' },
  { title: 'Compare',  href: '/compare',  icon: GitCompareArrows, desc: 'Real vs proposal' },
  { title: 'What-If',  href: '/what-if',  icon: Sliders,          desc: 'Simulate scenarios' },
  { title: 'Insights', href: '/insights', icon: TrendingUp,       desc: 'Inefficiency patterns' },
]

export function AppSidebar() {
  const pathname = usePathname()
  const { user, logout } = useAuth()

  const initials = user?.full_name
    ?.split(' ')
    .map((n) => n[0])
    .join('')
    .toUpperCase() || 'U'

  return (
    <Sidebar className="border-r border-sidebar-border">
      {/* Brand header */}
      <SidebarHeader className="px-4 py-5">
        <div className="flex items-center gap-3">
          <div className="relative flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-lg bg-primary shadow-sm">
            <span className="text-sm font-black text-primary-foreground tracking-tighter">LW</span>
          </div>
          <div className="flex flex-col">
            <span className="font-bold text-[15px] tracking-tight leading-tight">LineWise</span>
            <span className="text-[10px] text-muted-foreground font-semibold uppercase tracking-[0.12em]">
              Damm Operations
            </span>
          </div>
        </div>
        {/* Demo week badge */}
        <div className="mt-3 flex items-center gap-1.5 rounded-md bg-muted px-2.5 py-1.5">
          <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 flex-shrink-0" />
          <span className="text-[11px] text-muted-foreground font-medium">Demo week · 18–24 May 2026</span>
        </div>
      </SidebarHeader>

      <SidebarSeparator />

      <SidebarContent className="px-2 py-3">
        <SidebarGroup>
          <SidebarGroupLabel className="px-3 text-[10px] font-semibold uppercase tracking-[0.1em] text-muted-foreground/60 mb-1">
            Navigation
          </SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu className="gap-0.5">
              {navItems.map((item) => {
                const isActive = pathname.startsWith(item.href)
                return (
                  <SidebarMenuItem key={item.href}>
                    <Link
                      href={item.href}
                      aria-current={isActive ? 'page' : undefined}
                      className={cn(
                        'group relative flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-all duration-150',
                        isActive
                          ? 'bg-primary/10 text-primary'
                          : 'text-muted-foreground hover:bg-muted hover:text-foreground'
                      )}
                    >
                      {/* Left accent bar */}
                      <span
                        className={cn(
                          'absolute left-0 inset-y-1.5 w-[2.5px] rounded-full transition-all duration-150',
                          isActive ? 'bg-primary opacity-100' : 'opacity-0'
                        )}
                      />
                      <item.icon
                        className={cn(
                          'h-4 w-4 flex-shrink-0 transition-colors duration-150',
                          isActive ? 'text-primary' : 'text-muted-foreground group-hover:text-foreground'
                        )}
                      />
                      <span className={isActive ? 'font-semibold' : ''}>{item.title}</span>
                    </Link>
                  </SidebarMenuItem>
                )
              })}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>

      <SidebarFooter className="p-2 pb-3">
        <SidebarSeparator className="mb-2" />
        <div className="flex items-center gap-3 rounded-lg px-2 py-2">
          <Avatar className="h-8 w-8 flex-shrink-0">
            <AvatarFallback className="bg-primary/10 text-primary text-xs font-semibold">
              {initials}
            </AvatarFallback>
          </Avatar>
          <div className="flex flex-1 flex-col overflow-hidden">
            <span className="truncate text-sm font-medium leading-tight">{user?.full_name || 'Operador'}</span>
            <span className="truncate text-xs text-muted-foreground leading-tight mt-0.5">{user?.email}</span>
          </div>
          <button
            onClick={() => logout()}
            aria-label="Sign out"
            className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-md text-muted-foreground hover:bg-destructive/10 hover:text-destructive"
          >
            <LogOut className="h-3.5 w-3.5" />
          </button>
        </div>
      </SidebarFooter>
    </Sidebar>
  )
}
