import { StartSessionRequest, StartSessionResponse } from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:8000/api/v1";

export async function startInterview(payload: StartSessionRequest): Promise<StartSessionResponse> {
  const response = await fetch(`${API_BASE}/sessions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
  if (!response.ok) {
    throw new Error("Failed to start interview session.");
  }
  return response.json();
}

export async function submitAnswer(
  sessionId: string,
  token: string,
  questionId: string,
  answerText: string
): Promise<{ status: string; message: string }> {
  const response = await fetch(`${API_BASE}/sessions/${sessionId}/answers`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Session-Token": token
    },
    body: JSON.stringify({
      question_id: questionId,
      answer_text: answerText
    })
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error?.detail?.message ?? "Answer submission failed.");
  }
  return response.json();
}

export async function getReport(sessionId: string, token: string): Promise<Record<string, unknown>> {
  const response = await fetch(`${API_BASE}/sessions/${sessionId}/report`, {
    headers: { "X-Session-Token": token }
  });
  if (!response.ok) {
    throw new Error("Failed to fetch report.");
  }
  return response.json();
}
