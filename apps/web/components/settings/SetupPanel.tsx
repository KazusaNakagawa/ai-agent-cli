import Link from "next/link"

import { Button } from "@/components/ui/button"

// Opens the wizard in re-run mode. Server state is left alone, so closing the
// tab or navigating away mid-wizard never locks the app.
export function SetupPanel() {
  return (
    <div className="space-y-3 text-sm">
      <p className="text-muted-foreground">
        Walk through the first-run wizard again: auth mode, portfolio,
        notifications and a dry-run check. It starts from your current
        settings, and sectors, events and conflicts are left as they are.
      </p>
      <Button asChild>
        <Link href="/?rerun=1" data-testid="rerun-setup">
          Re-run setup wizard
        </Link>
      </Button>
    </div>
  )
}
