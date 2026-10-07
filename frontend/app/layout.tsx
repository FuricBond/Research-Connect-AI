import type { Metadata } from "next";
import { AppHeader } from "../components/AppHeader";
import { DiscoveryNavbar } from "../components/discovery/DiscoveryNavbar";
import { SessionProvider } from "../components/auth/SessionProvider";
import { THEME_INIT_SCRIPT } from "../utils/theme";
import { fontVariables } from "./fonts";
// The design system first (tokens, then element defaults), then the legacy page stylesheets,
// whose class rules still win over element defaults while pages are migrated.
import "../styles/tokens.css";
import "../styles/base.css";
import "../styles/globals.css";
// The header's identity control and the route guards render on every page, so their
// styling is loaded here rather than per page.
import "../styles/auth.css";
// Utility classes used by the personalization and unified-intelligence panels.
import "../styles/tailwind.css";

export const metadata: Metadata = {
  title: "ResearchConnect AI — Academic Intelligence & Discovery",
  description:
    "ResearchConnect AI is an academic intelligence platform offering multi-channel hybrid discovery, semantic literature search, predatory-risk analysis, and deadline intelligence for researchers.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    // data-theme is set before first paint by THEME_INIT_SCRIPT (light, dark, or the system's),
    // so the server's "light" may differ from the attribute React finds: that is expected.
    <html lang="en" className={fontVariables} data-theme="light" suppressHydrationWarning>
      <head>
        <meta name="viewport" content="width=device-width, initial-scale=1.0" />
        <script dangerouslySetInnerHTML={{ __html: THEME_INIT_SCRIPT }} />
      </head>
      <body>
        <a className="rc-skip-link" href="#main-content">
          Skip to main content
        </a>
        {/* One session for the whole application: the header, the navigation and every
            page read the signed-in account from here. */}
        <SessionProvider>
          <div className="app-shell">
            <AppHeader />
            <DiscoveryNavbar />
            <main id="main-content" className="main-content" tabIndex={-1}>
              {children}
            </main>
          </div>
        </SessionProvider>
      </body>
    </html>
  );
}
