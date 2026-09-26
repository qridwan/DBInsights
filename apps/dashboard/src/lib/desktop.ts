// Native-app features, used only when the dashboard is running inside the DBInsight desktop app
// (Tauri). In a normal browser every function here reports "not available" and callers fall back.

interface TauriGlobal {
  dialog?: { open: (options: { directory?: boolean; multiple?: boolean; title?: string; defaultPath?: string }) => Promise<string | string[] | null> };
}

const tauri = (): TauriGlobal | undefined => (typeof window === "undefined" ? undefined : (window as unknown as { __TAURI__?: TauriGlobal }).__TAURI__);

export const isDesktop = (): boolean => Boolean(tauri()?.dialog);

/** The operating system's own "choose a folder" dialog. Returns the absolute path, or null if cancelled. */
export async function pickFolder(title = "Choose a project folder", defaultPath?: string): Promise<string | null> {
  const dialog = tauri()?.dialog;
  if (!dialog) return null;
  const chosen = await dialog.open({ directory: true, multiple: false, title, ...(defaultPath ? { defaultPath } : {}) });
  return Array.isArray(chosen) ? (chosen[0] ?? null) : chosen;
}
