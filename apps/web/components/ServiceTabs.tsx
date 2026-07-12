"use client"
import Link from "next/link"
import { usePathname } from "next/navigation"

import { SERVICES, serviceForPath } from "@/lib/services"
import { cn } from "@/lib/utils"

export function ServiceTabs() {
  const pathname = usePathname()
  const activeId = serviceForPath(pathname).id

  return (
    <nav
      data-testid="service-tabs"
      aria-label="Services"
      className="flex items-center gap-1 border-b px-8 py-2"
    >
      {SERVICES.map((service) => {
        const active = service.id === activeId
        return (
          <Link
            key={service.id}
            href={service.defaultHref}
            data-testid={`service-tab-${service.id}`}
            aria-current={active ? "page" : undefined}
            className={cn(
              "rounded-md px-3 py-1.5 text-lg transition-colors",
              active
                ? "bg-accent text-accent-foreground"
                : "text-muted-foreground hover:bg-accent/50",
            )}
          >
            {service.icon}
            <span className="sr-only">{service.label}</span>
          </Link>
        )
      })}
    </nav>
  )
}
