import type { Metadata } from "next";

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
    <html lang="ru">
      <body
        style={{
          margin: 0,
          fontFamily:
            "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif",
        }}
      >
        {children}
      </body>
    </html>
  );
}
