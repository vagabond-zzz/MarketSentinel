export function activate(): void {
  // M4 will spawn the Python daemon and register StatusBar / Hover / commands.
}

export function deactivate(): void {
  // M4 will send shutdown, wait a short grace period, then terminate the child.
}
