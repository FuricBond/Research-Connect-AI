/**
 * The Content-Security-Policy sent with every page (Fix 6/9, audit SEC-02). The app loads nothing
 * from another origin (no web fonts, remote images, frames or third-party scripts; its doi.org,
 * ORCID and OpenAlex links are navigations, which this policy does not restrict), so everything is
 * same-origin except requests to the API. Scripts run from this origin or with this response's
 * nonce: Next.js's bootstrap scripts and the theme script, nothing else inline. Styles still allow
 * 'unsafe-inline' (inline style attributes and next/font); 'unsafe-eval' is only for the
 * development server's fast refresh.
 */
export function buildContentSecurityPolicy(apiUrl: string, nonce: string, isDevelopment: boolean): string {
  const apiOrigin = new URL(apiUrl).origin;
  const directives: [string, string[]][] = [
    ["default-src", ["'self'"]],
    ["script-src", ["'self'", `'nonce-${nonce}'`, ...(isDevelopment ? ["'unsafe-eval'"] : [])]],
    ["style-src", ["'self'", "'unsafe-inline'"]],
    ["font-src", ["'self'", "data:"]],
    ["img-src", ["'self'", "data:", "blob:"]],
    ["connect-src", ["'self'", apiOrigin]],
    ["object-src", ["'none'"]],
    ["base-uri", ["'self'"]],
    ["form-action", ["'self'"]],
    ["frame-ancestors", ["'none'"]],
  ];
  return directives.map(([name, sources]) => `${name} ${sources.join(" ")}`).join("; ");
}
