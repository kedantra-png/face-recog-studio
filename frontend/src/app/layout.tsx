import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "AuraFace | Anti-Spoofing AI Detection Platform",
  description: "Real-Time Face Anti-Spoofing & Liveness Detection System powered by Silent-Face Deep Learning & FastAPI",
  icons: {
    icon: 'data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><text y=".9em" font-size="90">🛡️</text></svg>',
  },
};


export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="dark">
      <body className="antialiased bg-[#090d16] text-slate-100 selection:bg-emerald-500 selection:text-white min-h-screen">
        {children}
      </body>
    </html>
  );
}
