"use client";

import { useState } from "react";
import { createResearcherProfile } from "../../services/api";
import type { AcademicStatus, ResearcherProfile } from "../../types/researcher";
import { academicStatusLabel } from "../../utils/personalization";
import { Button } from "../ui/Button/Button";
import { Select, TextInput } from "../ui/Field/Field";
import { Alert } from "../ui/State/State";
import styles from "./Profile.module.css";

const STAGES: AcademicStatus[] = ["UNDERGRADUATE", "POSTGRADUATE", "PHD", "POSTDOC", "FACULTY", "RESEARCHER", "OTHER"];

/**
 * For an account without a researcher profile (normally made at registration). Only what the
 * person enters is sent: no name, keywords or summary are filled in for them.
 */
export function CreateProfile({ email: givenEmail, onCreated }: { email?: string | null; onCreated: (profile: ResearcherProfile) => void }) {
  const [name, setName] = useState("");
  const [email, setEmail] = useState(givenEmail ?? "");
  const [stage, setStage] = useState<AcademicStatus>("PHD");
  const [institution, setInstitution] = useState("");
  const [department, setDepartment] = useState("");
  const [saving, setSaving] = useState(false);
  const [failed, setFailed] = useState(false);

  async function create(event: React.FormEvent) {
    event.preventDefault();
    setSaving(true);
    setFailed(false);
    try {
      onCreated(
        await createResearcherProfile({
          full_name: name.trim(),
          email: email.trim(),
          academic_status: stage,
          institution_name: institution.trim() || undefined,
          department: department.trim() || undefined,
        })
      );
    } catch {
      setFailed(true);
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className={styles.card} aria-labelledby="create-profile-heading">
      <h2 id="create-profile-heading" className={styles.cardTitle}>
        Create your researcher profile
      </h2>
      <p className={styles.text}>Your profile holds your career stage, institution and scholarly identifiers; your recommendations are built on it.</p>
      <form className={styles.form} onSubmit={create}>
        <div className={styles.formGrid}>
          <TextInput label="Full name" value={name} onChange={(event) => setName(event.target.value)} required autoComplete="name" />
          <TextInput label="Academic email" type="email" value={email} onChange={(event) => setEmail(event.target.value)} required autoComplete="email" />
          <Select label="Career stage" value={stage} onChange={(event) => setStage(event.target.value as AcademicStatus)}>
            {STAGES.map((value) => (
              <option key={value} value={value}>
                {academicStatusLabel(value)}
              </option>
            ))}
          </Select>
          <TextInput label="Institution" value={institution} onChange={(event) => setInstitution(event.target.value)} />
          <TextInput label="Department" value={department} onChange={(event) => setDepartment(event.target.value)} />
        </div>
        {failed && (
          <Alert tone="danger" announce>
            Your profile could not be created. Check the details and try again.
          </Alert>
        )}
        <div className={styles.formActions}>
          <Button type="submit" loading={saving}>
            Create profile
          </Button>
        </div>
      </form>
    </section>
  );
}
