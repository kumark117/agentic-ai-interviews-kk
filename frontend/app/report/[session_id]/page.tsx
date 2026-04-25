"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";

import { ReportView } from "../../../components/ReportView";
import { getReport } from "../../../lib/api";
import { useSessionStore } from "../../../lib/session-context";

export default function ReportPage() {
  const params = useParams<{ session_id: string }>();
  const sessionStore = useSessionStore();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [report, setReport] = useState<Record<string, unknown> | null>(null);

  useEffect(() => {
    if (!sessionStore.token || !sessionStore.sessionId || sessionStore.sessionId !== params.session_id) {
      setError("Session token unavailable. Restart from home page.");
      setLoading(false);
      return;
    }

    getReport(sessionStore.sessionId, sessionStore.token)
      .then((payload) => {
        setReport(payload);
      })
      .catch((e) => {
        setError((e as Error).message);
      })
      .finally(() => setLoading(false));
  }, [params.session_id, sessionStore]);

  return <ReportView report={report} loading={loading} error={error} />;
}
