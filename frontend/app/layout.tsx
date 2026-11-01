import type { Metadata } from "next";
import { headers } from "next/headers";
import { SessionProvider } from "../components/auth/SessionProvider";
import { AppShell } from "../components/shell/AppShell";
import { THEME_INIT_SCRIPT } from "../utils/theme";
import { fontVariables } from "./fonts";
// The design system first (tokens, then element defaults), then the legacy page stylesheets,
// whose class rules still win over element defaults while pages are migrated.
import "../styles/tokens.css";
import "../styles/base.css";
import "../styles/globals.css";
// Utility classes used by the personalization and unified-intelligence panels.
import "../styles/tailwind.css";

export const metadata: Metadata = {
  title: "ResearchConnect AI — Academic Intelligence & Discovery",
  description:
    "ResearchConnect AI is an academic intelligence platform offering multi-channel hybrid discovery, semantic literature search, predatory-risk analysis, and deadline intelligence for researchers.",
};

export default async function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  // Reading the request's headers also renders every page per request: a nonce only protects a page
  // that was rendered with it, so nothing can be prerendered (audit SEC-02).
  const nonce = (await headers()).get("x-nonce") ?? undefined;
  return (
    // data-theme is set before first paint by THEME_INIT_SCRIPT (light, dark, or the system's),
    // so the server's "light" may differ from the attribute React finds: that is expected.
    <html lang="en" className={fontVariables} data-theme="light" suppressHydrationWarning>
      <head>
        <meta name="viewport" content="width=device-width, initial-scale=1.0" />
        <script nonce={nonce} suppressHydrationWarning dangerouslySetInnerHTML={{ __html: THEME_INIT_SCRIPT }} />
      </head>
      <body>
        <a className="rc-skip-link" href="#main-content">
          Skip to main content
        </a>
        {/* One session for the whole application: the shell (header, navigation, account
            menu) and every page read the signed-in account from here. The shell renders the
            <main id="main-content"> the skip link targets. */}
        <SessionProvider>
          <AppShell>{children}</AppShell>
        </SessionProvider>
      </body>
    </html>
  );
}
