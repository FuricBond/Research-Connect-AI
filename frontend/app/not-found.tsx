import Link from "next/link";

/**
 * Next.js not-found.tsx — shown for unmatched routes.
 */
export default function NotFound() {
  return (
    <div className="state-container empty-state" style={{ marginTop: "4rem" }}>
      <h2>Page Not Found</h2>
      <p>The page you&apos;re looking for does not exist.</p>
      <Link href="/" className="action-btn primary-btn" style={{ marginTop: "1rem", display: "inline-flex" }}>
        Return to Literature Search
      </Link>
    </div>
  );
}
