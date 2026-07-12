export const dynamic = "force-dynamic"

import { WorkspaceScreen } from "@/components/screens/WorkspaceScreen"

export default function WorkspacePage() {
  return (
    <div className="space-y-4">
      <header>
        <h2 className="text-xl font-semibold">Workspace</h2>
        <p className="text-sm text-muted-foreground">
          Browse workspace files in the sidebar, then edit or preview them.
          Markdown files render a live preview.
        </p>
      </header>
      <WorkspaceScreen />
    </div>
  )
}
