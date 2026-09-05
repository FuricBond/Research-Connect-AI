import type { Metadata } from "next";
import { AppHeader } from "../components/AppHeader";
import { DiscoveryNavbar } from "../components/discovery/DiscoveryNavbar";
import "../styles/globals.css";

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
    <html lang="en">
      <head>
        <meta name="viewport" content="width=device-width, initial-scale=1.0" />
      </head>
      <body>
        <div className="app-shell">
          <AppHeader />
          <DiscoveryNavbar />
          <main className="main-content">{children}</main>
        </div>
      </body>
    </html>
  );
}
