export default function Home() {
  const apiUrl =
    process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

  return (
    <main style={{ padding: "2rem", maxWidth: 720 }}>
      <h1>Цифровой паспорт проекта</h1>
      <p>Frontend running. Next.js 14 + TypeScript.</p>
      <p>
        Backend API:{" "}
        <code
          style={{
            background: "#f0f0f0",
            padding: "2px 6px",
            borderRadius: 3,
          }}
        >
          {apiUrl}
        </code>
      </p>
      <p style={{ color: "#666", fontSize: 14 }}>
        Заглушка из задачи 0.2 (infrastructure). Полноценный UI появляется
        в Фазе 3 (роутинг, auth, список проектов).
      </p>
    </main>
  );
}
