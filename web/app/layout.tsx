import "./globals.css";
import type { ReactNode } from "react";

export const metadata = {
  title: "Agent X-Ray — Experiment Audit",
  description: "Component-level ablations and compute-matched evaluation for agentic workflows.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" className="bg-ink text-slate-100">
      <body>{children}</body>
    </html>
  );
}
