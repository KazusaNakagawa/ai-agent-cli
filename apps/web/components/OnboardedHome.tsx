import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"

export function OnboardedHome() {
  return (
    <Card className="w-full max-w-md">
      <CardHeader>
        <CardTitle>ai-agent</CardTitle>
        <CardDescription>Setup complete</CardDescription>
      </CardHeader>
      <CardContent className="text-sm text-muted-foreground">
        Main sidebar UI is coming in #71.
      </CardContent>
    </Card>
  )
}
