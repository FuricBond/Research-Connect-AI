import { Alert } from "../ui/State/State";

/**
 * Decision 1 (audit SEC-03): what a faculty account waiting for verification reads wherever it
 * would recruit. The API refuses regardless; this says why, and what happens next.
 */
export function VerificationNotice({ className }: { className?: string }) {
  return (
    <Alert tone="info" title="Your faculty account is waiting for verification" className={className}>
      An administrator needs to verify your account before you can create or publish research postings and receive applications. You do not need to do anything else; everything else on the platform works
      as usual in the meantime.
    </Alert>
  );
}
