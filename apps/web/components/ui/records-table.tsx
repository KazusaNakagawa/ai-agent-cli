import { ReactNode } from "react"

interface Column {
  label: string
  className?: string
}

interface RecordsTableProps {
  columns: Column[]
  children: ReactNode
}

/** Shared table shell used by Briefing and Journal record lists. */
export function RecordsTable({ columns, children }: RecordsTableProps) {
  return (
    <table className="w-full text-sm">
      <thead>
        <tr className="border-b bg-muted/50 text-left text-xs text-muted-foreground">
          {columns.map((col) => (
            <th key={col.label} className={col.className ?? "px-3 py-2"}>
              {col.label}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>{children}</tbody>
    </table>
  )
}
