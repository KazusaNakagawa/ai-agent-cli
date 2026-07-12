// Ambient declarations for the parts of the File System Access API we use that
// aren't yet in TypeScript's bundled lib.dom (directory iteration, permission
// queries, and the picker entrypoint). Chromium-only.

interface FileSystemPermissionDescriptor {
  mode?: "read" | "readwrite"
}

interface FileSystemHandle {
  queryPermission?(
    descriptor?: FileSystemPermissionDescriptor,
  ): Promise<PermissionState>
  requestPermission?(
    descriptor?: FileSystemPermissionDescriptor,
  ): Promise<PermissionState>
}

interface FileSystemDirectoryHandle {
  values(): AsyncIterableIterator<FileSystemHandle>
}

interface Window {
  showDirectoryPicker?(options?: {
    mode?: "read" | "readwrite"
  }): Promise<FileSystemDirectoryHandle>
}
