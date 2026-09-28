import "./globals.css";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "PROXY AI Claim Analysis",
  description: "Realtime AI insurance claim analysis dashboard",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return <html lang="en"><body>{children}</body></html>;
}
