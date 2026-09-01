export type FileKind = "image" | "pdf" | "document"

export function getFileKind(file: File): FileKind {
  if (file.type.startsWith("image/")) return "image"
  if (file.type === "application/pdf" || file.name.toLowerCase().endsWith(".pdf")) return "pdf"
  return "document"
}
