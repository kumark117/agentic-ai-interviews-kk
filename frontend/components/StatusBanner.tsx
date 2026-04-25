export function StatusBanner({ message }: { message: string | null }) {
  if (!message) return null;
  return <div className="card">{message}</div>;
}
