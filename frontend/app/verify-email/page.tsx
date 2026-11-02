import type { Metadata } from "next";
import { VerifyEmailPage } from "../../components/auth/VerifyEmailPage";

export const metadata: Metadata = {
  title: "Confirm your email address — ResearchConnect AI",
};

export default function VerifyEmailRoute() {
  return <VerifyEmailPage />;
}
