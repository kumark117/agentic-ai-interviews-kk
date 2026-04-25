export type Question = {
  question_id: string;
  text: string;
  difficulty: "easy" | "medium" | "hard";
};

export type EvaluationPayload = {
  question_id: string;
  score: number;
  feedback: string;
  confidence: "HIGH" | "LOW";
  fallback_flag: boolean;
  source: "llm" | "fallback_timeout";
};

export type SessionEvent = {
  event_id: string;
  event_seq: number;
  session_id: string;
  event_type:
    | "thinking"
    | "evaluation_started"
    | "evaluation_completed"
    | "question_generated"
    | "interview_completed"
    | "queue_delay"
    | "error";
  payload: Record<string, unknown>;
  created_at: string;
};

export type SessionState = {
  sessionId: string;
  token: string;
  status: "QUESTIONING" | "PROCESSING" | "END";
  currentQuestion: Question | null;
  feedback: EvaluationPayload | null;
  logs: SessionEvent[];
  isStreaming: boolean;
  lastSeenSeq: number;
};

export type StartSessionRequest = {
  candidate_id: string;
  candidate_name: string;
  role: string;
  experience_level: "junior" | "mid" | "senior";
  interview_type: "frontend_ai_fullstack" | "backend_systems" | "fullstack_general" | "data_ml" | "devops";
  max_questions: number;
};

export type StartSessionResponse = {
  session_id: string;
  session_token: string;
  status: "QUESTIONING";
  current_question: Question;
  stream_url: string;
};
