import { SessionEvent } from "../lib/types";

function summarize(event: SessionEvent): string {
  if (event.event_type === "thinking") return "Thinking...";
  if (event.event_type === "evaluation_started") return String(event.payload.question_id ?? "");
  if (event.event_type === "evaluation_completed") {
    return `score: ${String(event.payload.score ?? "")}, confidence: ${String(event.payload.confidence ?? "")}`;
  }
  if (event.event_type === "question_generated") return String(event.payload.question_id ?? "");
  if (event.event_type === "queue_delay") return String(event.payload.message ?? "Queue delay");
  if (event.event_type === "error") return String(event.payload.message ?? "Error");
  return "";
}

export function LogPanel({ logs }: { logs: SessionEvent[] }) {
  return (
    <section>
      <h3>Log Panel</h3>
      {logs.length === 0 ? (
        <p>No events yet.</p>
      ) : (
        <ul>
          {logs.map((event) => (
            <li key={event.event_id}>
              [{event.event_seq}] {event.event_type} — {summarize(event)}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
