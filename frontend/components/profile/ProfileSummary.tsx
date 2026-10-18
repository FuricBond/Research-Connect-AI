"use client";

import { useState } from "react";
import { ExternalLink, Save } from "lucide-react";
import { updateResearcherProfile } from "../../services/api";
import type { AcademicStatus, ResearcherProfile, ResearcherProfileUpdatePayload } from "../../types/researcher";
import { humanizeEnum } from "../../utils/date";
import { academicStatusLabel } from "../../utils/personalization";
import { TopicTags } from "../research/TopicTags";
import { Button } from "../ui/Button/Button";
import { Select, TextArea, TextInput } from "../ui/Field/Field";
import { Alert } from "../ui/State/State";
import styles from "./Profile.module.css";

const STAGES: AcademicStatus[] = ["UNDERGRADUATE", "POSTGRADUATE", "PHD", "POSTDOC", "FACULTY", "RESEARCHER", "OTHER", "UNKNOWN"];

/** The fields the completeness score checks, in the words the page uses. */
const FIELD: Record<string, string> = {
  full_name: "your name",
  academic_status: "your career stage",
  external_identity: "an ORCID iD or OpenAlex author ID",
};

function Completeness({ profile }: { profile: ResearcherProfile }) {
  const { percentage, level, missing_fields: missing } = profile.completeness;
  return (
    <div className={styles.completeness}>
      <p className={styles.notice}>
        Profile completeness {percentage}% — {humanizeEnum(level)}
      </p>
      <svg className={styles.bar} viewBox="0 0 100 6" preserveAspectRatio="none" aria-hidden="true" focusable="false">
        <rect className={styles.barTrack} x="0" y="0" width="100" height="6" rx="3" />
        {percentage > 0 && <rect className={styles.barFill} x="0" y="0" width={Math.min(100, percentage)} height="6" rx="3" />}
      </svg>
      {missing.length > 0 && <p className={styles.muted}>Still to add: {missing.map((field) => FIELD[field] ?? humanizeEnum(field).toLowerCase()).join(", ")}.</p>}
    </div>
  );
}

function EditForm({ profile, onCancel, onSaved }: { profile: ResearcherProfile; onCancel: () => void; onSaved: (profile: ResearcherProfile) => void }) {
  const [name, setName] = useState(profile.full_name);
  const [stage, setStage] = useState<AcademicStatus>(profile.academic_status);
  const [institution, setInstitution] = useState(profile.institution_name ?? "");
  const [department, setDepartment] = useState(profile.department ?? "");
  const [bio, setBio] = useState(profile.bio ?? "");
  const [orcid, setOrcid] = useState(profile.orcid ?? "");
  const [openalex, setOpenalex] = useState(profile.openalex_id ?? "");
  const [keywords, setKeywords] = useState(profile.keywords.join(", "));
  const [saving, setSaving] = useState(false);
  const [failed, setFailed] = useState(false);

  async function save(event: React.FormEvent) {
    event.preventDefault();
    setSaving(true);
    setFailed(false);
    const payload: ResearcherProfileUpdatePayload = {
      full_name: name.trim() || undefined,
      academic_status: stage,
      institution_name: institution.trim() || null,
      department: department.trim() || null,
      bio: bio.trim() || null,
      orcid: orcid.trim() || null,
      openalex_id: openalex.trim() || null,
      keywords: keywords
        .split(",")
        .map((keyword) => keyword.trim())
        .filter(Boolean),
    };
    try {
      onSaved(await updateResearcherProfile(profile.id, payload));
    } catch {
      setFailed(true);
    } finally {
      setSaving(false);
    }
  }

  return (
    <form className={styles.form} onSubmit={save} aria-label="Edit your profile">
      <div className={styles.formGrid}>
        <TextInput label="Full name" value={name} onChange={(event) => setName(event.target.value)} required />
        <Select label="Career stage" value={stage} onChange={(event) => setStage(event.target.value as AcademicStatus)}>
          {STAGES.map((value) => (
            <option key={value} value={value}>
              {academicStatusLabel(value) ?? "Not stated"}
            </option>
          ))}
        </Select>
        <TextInput label="Institution" value={institution} onChange={(event) => setInstitution(event.target.value)} />
        <TextInput label="Department or laboratory" value={department} onChange={(event) => setDepartment(event.target.value)} />
        <TextInput label="ORCID iD" hint="For example 0000-0002-1825-0097, or the full ORCID link." value={orcid} onChange={(event) => setOrcid(event.target.value)} />
        <TextInput label="OpenAlex author ID" hint="For example A5048491430, or the full OpenAlex link." value={openalex} onChange={(event) => setOpenalex(event.target.value)} />
      </div>
      <TextArea label="Research summary" rows={3} value={bio} onChange={(event) => setBio(event.target.value)} />
      <TextInput
        label="Research keywords"
        hint="Separate keywords with commas, for example: natural language processing, information retrieval."
        value={keywords}
        onChange={(event) => setKeywords(event.target.value)}
      />
      {failed && (
        <Alert tone="danger" announce>
          Your profile could not be saved. Check the identifiers and try again.
        </Alert>
      )}
      <div className={styles.formActions}>
        <Button variant="secondary" onClick={onCancel} disabled={saving}>
          Cancel
        </Button>
        <Button type="submit" loading={saving} leadingIcon={<Save size={16} aria-hidden="true" />}>
          Save changes
        </Button>
      </div>
    </form>
  );
}

/**
 * The profile summary (plan §12): completeness and what is missing, the scholarly identifiers
 * that link publications, the research summary and keywords — and the same fields to edit.
 */
export function ProfileSummary({ profile, editing, onEditing, onSaved }: { profile: ResearcherProfile; editing: boolean; onEditing: (editing: boolean) => void; onSaved: (profile: ResearcherProfile) => void }) {
  const [notice, setNotice] = useState("");
  return (
    <section className={styles.card} aria-labelledby="profile-summary-heading">
      <div className={styles.cardHead}>
        <h2 id="profile-summary-heading" className={styles.cardTitle}>
          {editing ? "Edit your profile" : "Profile"}
        </h2>
      </div>
      {editing ? (
        <EditForm
          profile={profile}
          onCancel={() => onEditing(false)}
          onSaved={(updated) => {
            onSaved(updated);
            onEditing(false);
            setNotice("Your profile is saved. Topics from your publications are being worked out again.");
          }}
        />
      ) : (
        <>
          <Completeness profile={profile} />
          <div className={styles.completeness}>
            <h3 className={styles.subTitle}>Scholarly identifiers</h3>
            {profile.orcid || profile.openalex_id ? (
              <ul className={styles.identifiers}>
                {profile.orcid && (
                  <li>
                    <a className={styles.link} href={`https://orcid.org/${profile.orcid}`} target="_blank" rel="noopener noreferrer">
                      ORCID {profile.orcid}
                      <ExternalLink size={14} aria-hidden="true" />
                      <span className="rc-visually-hidden"> (opens in new tab)</span>
                    </a>
                  </li>
                )}
                {profile.openalex_id && (
                  <li>
                    <a className={styles.link} href={`https://openalex.org/${profile.openalex_id}`} target="_blank" rel="noopener noreferrer">
                      OpenAlex {profile.openalex_id}
                      <ExternalLink size={14} aria-hidden="true" />
                      <span className="rc-visually-hidden"> (opens in new tab)</span>
                    </a>
                  </li>
                )}
              </ul>
            ) : (
              <p className={styles.muted}>None yet. Add an ORCID iD or OpenAlex author ID to link your publications.</p>
            )}
            {profile.canonical_researcher_id && <p className={styles.muted}>Linked to a scholarly record.</p>}
          </div>
          {profile.bio && (
            <div className={styles.completeness}>
              <h3 className={styles.subTitle}>Research summary</h3>
              <p className={styles.text}>{profile.bio}</p>
            </div>
          )}
          {profile.keywords.length > 0 && (
            <div className={styles.completeness}>
              <h3 className={styles.subTitle}>Keywords</h3>
              <TopicTags topics={profile.keywords} label="Research keywords" />
            </div>
          )}
        </>
      )}
      <p role="status" className={styles.notice}>
        {notice}
      </p>
    </section>
  );
}
