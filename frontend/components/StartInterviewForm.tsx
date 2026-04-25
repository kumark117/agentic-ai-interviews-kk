"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

import { startInterview } from "../lib/api";
import { useSessionStore } from "../lib/session-context";
import { StartSessionRequest } from "../lib/types";

export function StartInterviewForm() {
  const router = useRouter();
  const sessionStore = useSessionStore();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [maxQuestionsInput, setMaxQuestionsInput] = useState("8");
  const parsedMaxQuestions = Number(maxQuestionsInput);
  const maxQuestionsValid =
    maxQuestionsInput.trim() !== "" &&
    Number.isInteger(parsedMaxQuestions) &&
    parsedMaxQuestions >= 1 &&
    parsedMaxQuestions <= 20;

  const [form, setForm] = useState<StartSessionRequest>({
    candidate_id: "cand_123",
    candidate_name: "Kumar",
    role: "Senior React + AI Engineer",
    experience_level: "senior",
    interview_type: "frontend_ai_fullstack",
    max_questions: 8
  });
  const normalizedCandidateName = form.candidate_name.trim();
  const candidateNameAllowedPattern = /^[A-Za-z .'-]+$/;
  const candidateNameCharsetValid =
    normalizedCandidateName.length === 0 || candidateNameAllowedPattern.test(normalizedCandidateName);
  const candidateNameValid =
    normalizedCandidateName.length >= 2 &&
    normalizedCandidateName.length <= 80 &&
    candidateNameCharsetValid;

  async function onStart() {
    setError(null);
    if (!candidateNameCharsetValid) {
      setError("Candidate Name can contain letters, spaces, apostrophe ('), hyphen (-), and dot (.) only.");
      return;
    }
    if (!candidateNameValid) {
      setError("Candidate Name must be 2 to 80 characters.");
      return;
    }
    if (!Number.isInteger(parsedMaxQuestions) || parsedMaxQuestions < 1 || parsedMaxQuestions > 20) {
      setError("Max Questions must be an integer between 1 and 20.");
      return;
    }

    setLoading(true);
    try {
      const response = await startInterview({
        ...form,
        candidate_name: normalizedCandidateName,
        max_questions: parsedMaxQuestions
      });
      sessionStore.setSession(response.session_id, response.session_token, response.current_question);
      router.push(`/interview/${response.session_id}`);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <main>
      <h1>Start Interview</h1>
      <section>
        <label>
          Candidate ID
          <p style={{ marginTop: 8, marginBottom: 12 }}>{form.candidate_id}</p>
          <p style={{ opacity: 0.75, marginTop: -8 }}>Auto-assigned for this demo form.</p>
        </label>
        <label>
          Candidate Name
          <input
            value={form.candidate_name}
            maxLength={80}
            onChange={(e) => setForm((prev) => ({ ...prev, candidate_name: e.target.value }))}
            style={!candidateNameValid ? { borderColor: "#ff4d4f", boxShadow: "0 0 0 1px #ff4d4f" } : undefined}
          />
          {!candidateNameCharsetValid ? (
            <p style={{ color: "#ff8a8a", marginTop: -6 }}>
              Allowed: letters, spaces, apostrophe ('), hyphen (-), dot (.).
            </p>
          ) : null}
          {candidateNameCharsetValid && !candidateNameValid ? (
            <p style={{ color: "#ff8a8a", marginTop: -6 }}>Name must be 2 to 80 characters.</p>
          ) : null}
        </label>
        <label>
          Role
          <input value={form.role} readOnly />
          <p style={{ opacity: 0.75, marginTop: -8 }}>Locked for current interview template.</p>
        </label>
        <label>
          Max Questions
          <input
            type="number"
            min={1}
            max={20}
            value={maxQuestionsInput}
            onChange={(e) => setMaxQuestionsInput(e.target.value)}
            onBlur={() => {
              if (maxQuestionsInput.trim() === "") {
                setMaxQuestionsInput("8");
                return;
              }
              const value = Number(maxQuestionsInput);
              if (!Number.isFinite(value)) {
                setMaxQuestionsInput("8");
                return;
              }
              const clamped = Math.min(20, Math.max(1, Math.trunc(value)));
              setMaxQuestionsInput(String(clamped));
            }}
            style={!maxQuestionsValid ? { borderColor: "#ff4d4f", boxShadow: "0 0 0 1px #ff4d4f" } : undefined}
          />
          {!maxQuestionsValid ? <p style={{ color: "#ff8a8a", marginTop: -6 }}>Enter an integer between 1 and 20.</p> : null}
          <p style={{ opacity: 0.85, marginTop: 0 }}>
            Applied only when starting a new interview session.
          </p>
        </label>
        <button type="button" onClick={onStart} disabled={loading}>
          {loading ? "Starting..." : "Start Interview"}
        </button>
        {error ? <p>{error}</p> : null}
      </section>
    </main>
  );
}
