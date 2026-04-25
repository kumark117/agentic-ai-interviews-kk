"use client";

import { createContext, useContext, useMemo, useState } from "react";

import { Question } from "./types";

type SessionStore = {
  sessionId: string | null;
  token: string | null;
  currentQuestion: Question | null;
  setSession: (sessionId: string, token: string, question: Question) => void;
  setCurrentQuestion: (question: Question | null) => void;
  clearSession: () => void;
};

const SessionContext = createContext<SessionStore | undefined>(undefined);

export function SessionProvider({ children }: { children: React.ReactNode }) {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [currentQuestion, setCurrentQuestion] = useState<Question | null>(null);

  const value = useMemo<SessionStore>(
    () => ({
      sessionId,
      token,
      currentQuestion,
      setSession: (nextSessionId, nextToken, question) => {
        setSessionId(nextSessionId);
        setToken(nextToken);
        setCurrentQuestion(question);
      },
      setCurrentQuestion,
      clearSession: () => {
        setSessionId(null);
        setToken(null);
        setCurrentQuestion(null);
      }
    }),
    [sessionId, token, currentQuestion]
  );

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSessionStore() {
  const context = useContext(SessionContext);
  if (!context) {
    throw new Error("useSessionStore must be used within SessionProvider.");
  }
  return context;
}
