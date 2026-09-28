import { Instrument_Serif, Inter, JetBrains_Mono } from "next/font/google";
import "./aperture.css";

const display = Instrument_Serif({
  subsets: ["latin"],
  weight: "400",
  variable: "--font-aperture-display",
});

const body = Inter({
  subsets: ["latin"],
  variable: "--font-aperture-body",
});

const mono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-aperture-mono",
});

export default function MarketingLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className={`aperture-page ${display.variable} ${body.variable} ${mono.variable}`}>
      {children}
    </div>
  );
}
