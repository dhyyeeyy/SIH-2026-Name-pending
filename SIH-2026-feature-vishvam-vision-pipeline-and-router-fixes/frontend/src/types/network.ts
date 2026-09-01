export interface NetworkEvent {
  id: string
  time: string
  protocol: "HTTP" | "IPC"
  destination: string
  label: string
}
