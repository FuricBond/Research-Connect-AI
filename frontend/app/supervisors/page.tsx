"use client";

import { RequireAuth } from "../../components/auth/RequireAuth";
import { SupervisorsPage } from "../../components/people/SupervisorsPage";

/** /supervisors (P6): suggested supervisors for student accounts; the backend enforces the role. */
export default function SupervisorDiscoveryPageRoute() {
  return (
    <RequireAuth>
      <SupervisorsPage />
    </RequireAuth>
  );
}
