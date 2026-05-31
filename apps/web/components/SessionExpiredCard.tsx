import { Card, CardContent } from "@/components/ui/card"

export function SessionExpiredCard() {
  return (
    <Card>
      <CardContent
        className="space-y-2 pt-6 text-sm"
        data-testid="session-expired"
      >
        <p className="font-medium text-destructive">Session expired</p>
        <p className="text-muted-foreground">
          The bearer token in <code className="font-mono">apps/web/.token</code>
          {" "}no longer matches{" "}
          <code className="font-mono">~/.ai-agent/session-token</code>.
          Restart the dev server (<code className="font-mono">bin/serve.sh</code>)
          to mirror a fresh token and refresh this page.
        </p>
      </CardContent>
    </Card>
  )
}
