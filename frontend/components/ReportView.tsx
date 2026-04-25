export function ReportView({
  report,
  loading,
  error
}: {
  report: Record<string, unknown> | null;
  loading: boolean;
  error: string | null;
}) {
  if (loading) return <main>Loading report...</main>;
  if (error) return <main>{error}</main>;
  if (!report) return <main>No report found.</main>;

  return (
    <main>
      <h1>Interview Report</h1>
      {report.is_complete === false ? <p>Partial report — interview ended before completion.</p> : null}
      <section>
        <pre>{JSON.stringify(report, null, 2)}</pre>
      </section>
    </main>
  );
}
