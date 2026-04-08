import type { Metadata } from "next";
import { Inter } from "next/font/google";

import { AuthProvider } from "@/components/auth-provider";
import { cn } from "@/lib/utils";

import "./globals.css";

// Geist шрифт доступен только в Next.js 15+. У нас 14.2 — используем Inter.
const inter = Inter({
  subsets: ["latin", "cyrillic"],
  variable: "--font-sans",
});

export const metadata: Metadata = {
  title: "Цифровой паспорт проекта",
  description:
    "Корпоративная система расчёта и управления проектами вывода SKU на рынок",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="ru" className={cn("font-sans", inter.variable)}>
      <body className="min-h-screen bg-background text-foreground antialiased">
        <AuthProvider>{children}</AuthProvider>
      </body>
    </html>
  );
}
