import "./globals.css";

import { SessionProvider } from "../lib/session-context";

export const metadata = {
  title: "AI Agentic Interview",
  description: "Event-driven AI interview frontend"
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <SessionProvider>{children}</SessionProvider>
      </body>
    </html>
  );
}
