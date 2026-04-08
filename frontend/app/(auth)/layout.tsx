/**
 * Layout для публичных auth-страниц (/login).
 *
 * Без sidebar, центрированная карточка. Не требует авторизации.
 * Если уже авторизован — `(auth)/login/page.tsx` сам редиректит на /projects.
 */
export default function AuthLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-muted/40 p-4">
      {children}
    </div>
  );
}
