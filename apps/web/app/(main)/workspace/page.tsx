export const dynamic = "force-dynamic"

import { FileFinder } from "@/components/workspace/FileFinder"
import { WorkspaceScreen } from "@/components/screens/WorkspaceScreen"

export default function WorkspacePage() {
  return (
    <div className="space-y-4">
      <header className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-xl font-semibold">Workspace</h2>
          <p className="text-sm text-muted-foreground">
            Browse workspace files in the sidebar, then edit or preview them.
            Markdown files render a live preview.
          </p>
        </div>
        <FileFinder />
      </header>
      <WorkspaceScreen />
    </div>
  )
}
