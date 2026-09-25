import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "AI Risk Check | Analyse de conformité",
  description: "Analysez les risques liés à l'IA de votre projet au regard de l'AI Act.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="fr" className="h-full antialiased">
      <body className="min-h-full flex flex-col">{children}</body>
    </html>
  );
}
