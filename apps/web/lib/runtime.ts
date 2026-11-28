/** True when the Web UI runs from the Docker image, which sets the marker. */
export function isDockerRuntime(env: Record<string, string | undefined>): boolean {
  return env.BRIEF_LENS_RUNTIME === "docker"
}
