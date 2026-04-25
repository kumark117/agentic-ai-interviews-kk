import { SessionEvent } from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:8000/api/v1";

export function connectSessionStream(
  sessionId: string,
  token: string,
  onEvent: (event: SessionEvent) => void,
  onError: () => void
): EventSource {
  const streamUrl = `${API_BASE}/sessions/${sessionId}/stream?token=${encodeURIComponent(token)}`;
  const source = new EventSource(streamUrl);

  source.onmessage = (message) => {
    const event = JSON.parse(message.data) as SessionEvent;
    onEvent(event);
  };

  source.onerror = () => {
    onError();
  };

  return source;
}
