"use client";

// Catches errors thrown in the root layout itself. Must render its own
// <html>/<body> because it replaces the root layout when triggered.
export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <html lang="en">
      <body>
        <main
          style={{
            minHeight: "100vh",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            padding: "2rem",
            fontFamily: "system-ui, sans-serif",
          }}
        >
          <div style={{ maxWidth: 420 }}>
            <h1 style={{ fontSize: "1.125rem", fontWeight: 600 }}>
              Something went wrong
            </h1>
            <p style={{ marginTop: 8, color: "#555", fontSize: "0.875rem" }}>
              {error.message || "A fatal error occurred."}
            </p>
            <button
              onClick={() => reset()}
              style={{
                marginTop: 16,
                padding: "0.5rem 1rem",
                borderRadius: 6,
                border: "1px solid #ccc",
                cursor: "pointer",
              }}
            >
              Try again
            </button>
          </div>
        </main>
      </body>
    </html>
  );
}
