"use client";

import { RequireAuth } from "../../../components/auth/RequireAuth";
import { PreferencesPage } from "../../../components/preferences/PreferencesPage";

export default function ResearcherPreferencesPageRoute() {
  return (
    <RequireAuth roles={["STUDENT", "FACULTY"]}>
      <PreferencesPage />
    </RequireAuth>
  );
}
