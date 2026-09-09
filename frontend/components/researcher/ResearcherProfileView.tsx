"use client";

import React, { useState } from "react";
import {
  BookOpen,
  Building2,
  ExternalLink,
  GraduationCap,
  Mail,
  Pencil,
  Save,
  Tag,
  User,
  X,
  FileText,
  AlertCircle,
  Check,
} from "lucide-react";
import type {
  AcademicStatus,
  ResearcherProfile,
  ResearcherProfileUpdatePayload,
  ResearcherWorkSummary,
} from "../../types/researcher";
import { ProfileCompletenessBadge } from "./ProfileCompletenessBadge";
import { updateResearcherProfile } from "../../services/api";

interface ResearcherProfileViewProps {
  profile: ResearcherProfile;
  initialWorks?: ResearcherWorkSummary[];
  onProfileUpdated?: (updated: ResearcherProfile) => void;
}

const ACADEMIC_STATUS_OPTIONS: AcademicStatus[] = [
  "UNDERGRADUATE",
  "POSTGRADUATE",
  "PHD",
  "POSTDOC",
  "FACULTY",
  "RESEARCHER",
  "OTHER",
  "UNKNOWN",
];

export function ResearcherProfileView({
  profile: initialProfile,
  initialWorks = [],
  onProfileUpdated,
}: ResearcherProfileViewProps) {
  const [profile, setProfile] = useState<ResearcherProfile>(initialProfile);
  const [works] = useState<ResearcherWorkSummary[]>(initialWorks);
  const [isEditing, setIsEditing] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  // Form State
  const [fullName, setFullName] = useState(profile.full_name);
  const [academicStatus, setAcademicStatus] = useState<AcademicStatus>(profile.academic_status);
  const [institutionName, setInstitutionName] = useState(profile.institution_name || "");
  const [department, setDepartment] = useState(profile.department || "");
  const [bio, setBio] = useState(profile.bio || "");
  const [orcid, setOrcid] = useState(profile.orcid || "");
  const [openalexId, setOpenalexId] = useState(profile.openalex_id || "");
  const [keywordsText, setKeywordsText] = useState(profile.keywords.join(", "));

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSaving(true);
    setErrorMessage(null);
    setSuccessMessage(null);

    const keywordsList = keywordsText
      .split(",")
      .map((k) => k.trim())
      .filter(Boolean);

    const payload: ResearcherProfileUpdatePayload = {
      full_name: fullName.trim() || undefined,
      academic_status: academicStatus,
      institution_name: institutionName.trim() || null,
      department: department.trim() || null,
      bio: bio.trim() || null,
      orcid: orcid.trim() || null,
      openalex_id: openalexId.trim() || null,
      keywords: keywordsList,
    };

    try {
      const updated = await updateResearcherProfile(profile.id, payload);
      setProfile(updated);
      setIsEditing(false);
      setSuccessMessage("Profile updated successfully.");
      if (onProfileUpdated) {
        onProfileUpdated(updated);
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to update profile";
      setErrorMessage(msg);
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div style={{ maxWidth: "1000px", margin: "0 auto", padding: "24px 16px" }}>
      {/* Notice Banner */}
      <div
        style={{
          background: "#f0fdf4",
          border: "1px solid #bbf7d0",
          borderRadius: "var(--radius-md)",
          padding: "12px 16px",
          marginBottom: "20px",
          fontSize: "13px",
          color: "#166534",
          display: "flex",
          alignItems: "center",
          gap: "8px",
        }}
      >
        <GraduationCap size={18} color="#0f766e" />
        <span>
          <strong>Phase 3.1: Researcher Profile Foundation</strong> — Canonical identity and
          knowledge layer connectivity. Recommendations remain unpersonalized until Phase 3.4+.
        </span>
      </div>

      {/* Completeness Badge */}
      <ProfileCompletenessBadge completeness={profile.completeness} />

      {/* Feedback Messages */}
      {errorMessage && (
        <div
          style={{
            background: "#fef2f2",
            border: "1px solid #fecaca",
            color: "#991b1b",
            padding: "10px 14px",
            borderRadius: "var(--radius-sm)",
            marginBottom: "16px",
            display: "flex",
            alignItems: "center",
            gap: "8px",
            fontSize: "13px",
          }}
        >
          <AlertCircle size={16} />
          {errorMessage}
        </div>
      )}

      {successMessage && (
        <div
          style={{
            background: "#f0fdf4",
            border: "1px solid #bbf7d0",
            color: "#166534",
            padding: "10px 14px",
            borderRadius: "var(--radius-sm)",
            marginBottom: "16px",
            display: "flex",
            alignItems: "center",
            gap: "8px",
            fontSize: "13px",
          }}
        >
          <Check size={16} />
          {successMessage}
        </div>
      )}

      {/* Main Profile Card */}
      <div
        style={{
          background: "var(--bg-card)",
          border: "1px solid var(--border-color)",
          borderRadius: "var(--radius-lg)",
          boxShadow: "var(--shadow-sm)",
          padding: "28px",
          marginBottom: "24px",
        }}
      >
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "flex-start",
            flexWrap: "wrap",
            gap: "16px",
            borderBottom: "1px solid var(--border-color)",
            paddingBottom: "20px",
            marginBottom: "20px",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "16px" }}>
            <div
              style={{
                width: "64px",
                height: "64px",
                borderRadius: "var(--radius-full)",
                background: "var(--primary-subtle)",
                color: "var(--primary)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                border: "2px solid var(--primary-border)",
              }}
            >
              <User size={32} />
            </div>

            <div>
              <h1 style={{ margin: "0 0 4px 0", fontSize: "24px", fontWeight: 700 }}>
                {profile.full_name}
              </h1>
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "12px",
                  fontSize: "13px",
                  color: "var(--text-muted)",
                  flexWrap: "wrap",
                }}
              >
                {profile.email && (
                  <span style={{ display: "flex", alignItems: "center", gap: "4px" }}>
                    <Mail size={14} />
                    {profile.email}
                  </span>
                )}
                <span
                  style={{
                    background: "var(--bg-muted)",
                    padding: "2px 8px",
                    borderRadius: "var(--radius-full)",
                    fontSize: "11px",
                    fontWeight: 600,
                    color: "var(--primary)",
                  }}
                >
                  {profile.academic_status}
                </span>
                {profile.canonical_researcher_id && (
                  <span
                    style={{
                      background: "#e0f2fe",
                      color: "#0369a1",
                      padding: "2px 8px",
                      borderRadius: "var(--radius-full)",
                      fontSize: "11px",
                      fontWeight: 600,
                    }}
                  >
                    Canonical Scholar Linked
                  </span>
                )}
              </div>
            </div>
          </div>

          <button
            type="button"
            onClick={() => setIsEditing(!isEditing)}
            style={{
              display: "flex",
              alignItems: "center",
              gap: "6px",
              padding: "8px 14px",
              fontSize: "13px",
              fontWeight: 500,
              borderRadius: "var(--radius-sm)",
              border: "1px solid var(--border-color)",
              background: isEditing ? "var(--bg-muted)" : "var(--bg-card)",
              cursor: "pointer",
            }}
          >
            {isEditing ? (
              <>
                <X size={15} /> Cancel
              </>
            ) : (
              <>
                <Pencil size={15} /> Edit Profile
              </>
            )}
          </button>
        </div>

        {/* View or Edit Mode */}
        {isEditing ? (
          <form onSubmit={handleSave} style={{ display: "grid", gap: "16px" }}>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "16px" }}>
              <div>
                <label style={{ display: "block", fontSize: "12px", fontWeight: 600, marginBottom: "4px" }}>
                  Full Display Name
                </label>
                <input
                  type="text"
                  value={fullName}
                  onChange={(e) => setFullName(e.target.value)}
                  style={{
                    width: "100%",
                    padding: "8px 12px",
                    border: "1px solid var(--border-color)",
                    borderRadius: "var(--radius-sm)",
                  }}
                  required
                />
              </div>

              <div>
                <label style={{ display: "block", fontSize: "12px", fontWeight: 600, marginBottom: "4px" }}>
                  Academic Career Stage
                </label>
                <select
                  value={academicStatus}
                  onChange={(e) => setAcademicStatus(e.target.value as AcademicStatus)}
                  style={{
                    width: "100%",
                    padding: "8px 12px",
                    border: "1px solid var(--border-color)",
                    borderRadius: "var(--radius-sm)",
                    background: "#ffffff",
                  }}
                >
                  {ACADEMIC_STATUS_OPTIONS.map((status) => (
                    <option key={status} value={status}>
                      {status}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "16px" }}>
              <div>
                <label style={{ display: "block", fontSize: "12px", fontWeight: 600, marginBottom: "4px" }}>
                  Institution Name
                </label>
                <input
                  type="text"
                  value={institutionName}
                  onChange={(e) => setInstitutionName(e.target.value)}
                  placeholder="e.g. Stanford University"
                  style={{
                    width: "100%",
                    padding: "8px 12px",
                    border: "1px solid var(--border-color)",
                    borderRadius: "var(--radius-sm)",
                  }}
                />
              </div>

              <div>
                <label style={{ display: "block", fontSize: "12px", fontWeight: 600, marginBottom: "4px" }}>
                  Department / Laboratory
                </label>
                <input
                  type="text"
                  value={department}
                  onChange={(e) => setDepartment(e.target.value)}
                  placeholder="e.g. Computer Science"
                  style={{
                    width: "100%",
                    padding: "8px 12px",
                    border: "1px solid var(--border-color)",
                    borderRadius: "var(--radius-sm)",
                  }}
                />
              </div>
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "16px" }}>
              <div>
                <label style={{ display: "block", fontSize: "12px", fontWeight: 600, marginBottom: "4px" }}>
                  ORCID (e.g. 0000-0002-1825-0097)
                </label>
                <input
                  type="text"
                  value={orcid}
                  onChange={(e) => setOrcid(e.target.value)}
                  placeholder="0000-0002-1825-0097 or URL"
                  style={{
                    width: "100%",
                    padding: "8px 12px",
                    border: "1px solid var(--border-color)",
                    borderRadius: "var(--radius-sm)",
                  }}
                />
              </div>

              <div>
                <label style={{ display: "block", fontSize: "12px", fontWeight: 600, marginBottom: "4px" }}>
                  OpenAlex Author ID (e.g. A5048491430)
                </label>
                <input
                  type="text"
                  value={openalexId}
                  onChange={(e) => setOpenalexId(e.target.value)}
                  placeholder="A5048491430 or URL"
                  style={{
                    width: "100%",
                    padding: "8px 12px",
                    border: "1px solid var(--border-color)",
                    borderRadius: "var(--radius-sm)",
                  }}
                />
              </div>
            </div>

            <div>
              <label style={{ display: "block", fontSize: "12px", fontWeight: 600, marginBottom: "4px" }}>
                Research Bio &amp; Focus
              </label>
              <textarea
                value={bio}
                onChange={(e) => setBio(e.target.value)}
                rows={3}
                placeholder="Brief summary of research areas and goals..."
                style={{
                  width: "100%",
                  padding: "8px 12px",
                  border: "1px solid var(--border-color)",
                  borderRadius: "var(--radius-sm)",
                }}
              />
            </div>

            <div>
              <label style={{ display: "block", fontSize: "12px", fontWeight: 600, marginBottom: "4px" }}>
                Research Keywords (comma separated)
              </label>
              <input
                type="text"
                value={keywordsText}
                onChange={(e) => setKeywordsText(e.target.value)}
                placeholder="e.g. natural language processing, machine learning, information retrieval"
                style={{
                  width: "100%",
                  padding: "8px 12px",
                  border: "1px solid var(--border-color)",
                  borderRadius: "var(--radius-sm)",
                }}
              />
            </div>

            <div style={{ display: "flex", justifyContent: "flex-end", gap: "10px", marginTop: "8px" }}>
              <button
                type="button"
                onClick={() => setIsEditing(false)}
                disabled={isSaving}
                style={{
                  padding: "8px 16px",
                  borderRadius: "var(--radius-sm)",
                  border: "1px solid var(--border-color)",
                  background: "#ffffff",
                  cursor: "pointer",
                }}
              >
                Cancel
              </button>

              <button
                type="submit"
                disabled={isSaving}
                style={{
                  padding: "8px 18px",
                  borderRadius: "var(--radius-sm)",
                  border: "none",
                  background: "var(--primary)",
                  color: "#ffffff",
                  fontWeight: 600,
                  cursor: "pointer",
                  display: "flex",
                  alignItems: "center",
                  gap: "6px",
                }}
              >
                <Save size={16} />
                {isSaving ? "Saving..." : "Save Changes"}
              </button>
            </div>
          </form>
        ) : (
          <div style={{ display: "grid", gap: "20px" }}>
            {/* Institution & Department */}
            <div style={{ display: "flex", alignItems: "flex-start", gap: "12px" }}>
              <Building2 size={20} color="var(--primary)" style={{ marginTop: "2px" }} />
              <div>
                <div style={{ fontWeight: 600, fontSize: "15px" }}>
                  {profile.institution ? profile.institution.display_name : profile.institution_name || "No Institution Specified"}
                </div>
                <div style={{ fontSize: "13px", color: "var(--text-muted)" }}>
                  {profile.department || "No Department"}
                  {profile.institution?.country_code && ` · ${profile.institution.country_code}`}
                </div>
              </div>
            </div>

            {/* External Identifiers */}
            <div>
              <div style={{ fontSize: "12px", fontWeight: 600, color: "var(--text-muted)", marginBottom: "8px", textTransform: "uppercase" }}>
                External Scholarly Identifiers
              </div>
              <div style={{ display: "flex", gap: "10px", flexWrap: "wrap" }}>
                {profile.orcid ? (
                  <a
                    href={`https://orcid.org/${profile.orcid}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: "6px",
                      padding: "6px 12px",
                      borderRadius: "var(--radius-sm)",
                      background: "#f0fdf4",
                      border: "1px solid #bbf7d0",
                      color: "#166534",
                      fontSize: "12px",
                      textDecoration: "none",
                      fontWeight: 500,
                    }}
                  >
                    ORCID: {profile.orcid} <ExternalLink size={12} />
                  </a>
                ) : (
                  <span style={{ fontSize: "12px", color: "var(--text-subtle)" }}>No ORCID provided</span>
                )}

                {profile.openalex_id && (
                  <a
                    href={`https://openalex.org/${profile.openalex_id}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: "6px",
                      padding: "6px 12px",
                      borderRadius: "var(--radius-sm)",
                      background: "#f0f9ff",
                      border: "1px solid #bae6fd",
                      color: "#0369a1",
                      fontSize: "12px",
                      textDecoration: "none",
                      fontWeight: 500,
                    }}
                  >
                    OpenAlex: {profile.openalex_id} <ExternalLink size={12} />
                  </a>
                )}
              </div>
            </div>

            {/* Bio */}
            {profile.bio && (
              <div>
                <div style={{ fontSize: "12px", fontWeight: 600, color: "var(--text-muted)", marginBottom: "6px", textTransform: "uppercase" }}>
                  Research Overview
                </div>
                <p style={{ margin: 0, fontSize: "14px", lineHeight: "1.6", color: "var(--text-body)" }}>
                  {profile.bio}
                </p>
              </div>
            )}

            {/* Keywords */}
            {profile.keywords && profile.keywords.length > 0 && (
              <div>
                <div style={{ fontSize: "12px", fontWeight: 600, color: "var(--text-muted)", marginBottom: "8px", textTransform: "uppercase" }}>
                  Research Keywords
                </div>
                <div style={{ display: "flex", gap: "6px", flexWrap: "wrap" }}>
                  {profile.keywords.map((kw, i) => (
                    <span
                      key={i}
                      style={{
                        display: "flex",
                        alignItems: "center",
                        gap: "4px",
                        background: "var(--bg-muted)",
                        padding: "4px 10px",
                        borderRadius: "var(--radius-full)",
                        fontSize: "12px",
                        color: "var(--text-main)",
                      }}
                    >
                      <Tag size={12} color="var(--primary)" />
                      {kw}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Linked Scholarly Works Section */}
      <div
        style={{
          background: "var(--bg-card)",
          border: "1px solid var(--border-color)",
          borderRadius: "var(--radius-lg)",
          boxShadow: "var(--shadow-sm)",
          padding: "24px 28px",
        }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            marginBottom: "16px",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
            <BookOpen size={20} color="var(--primary)" />
            <h2 style={{ margin: 0, fontSize: "18px", fontWeight: 700 }}>
              Authored Scholarly Works ({works.length})
            </h2>
          </div>
        </div>

        {works.length === 0 ? (
          <div
            style={{
              padding: "24px",
              textAlign: "center",
              color: "var(--text-muted)",
              fontSize: "13px",
              background: "var(--bg-muted)",
              borderRadius: "var(--radius-md)",
            }}
          >
            No publications currently linked to this researcher identity.
            {profile.orcid || profile.openalex_id ? (
              <div style={{ marginTop: "4px", fontSize: "12px" }}>
                Identities recorded: ingestion layer will map works during scheduled synchronization.
              </div>
            ) : (
              <div style={{ marginTop: "4px", fontSize: "12px" }}>
                Add an ORCID or OpenAlex ID above to automatically associate your scholarly works.
              </div>
            )}
          </div>
        ) : (
          <div style={{ display: "grid", gap: "12px" }}>
            {works.map((work) => (
              <div
                key={work.id}
                style={{
                  padding: "14px 16px",
                  border: "1px solid var(--border-color)",
                  borderRadius: "var(--radius-md)",
                  background: "var(--bg-app)",
                }}
              >
                <div style={{ fontWeight: 600, fontSize: "14px", marginBottom: "4px" }}>
                  {work.title}
                </div>
                <div
                  style={{
                    display: "flex",
                    gap: "12px",
                    fontSize: "12px",
                    color: "var(--text-muted)",
                    flexWrap: "wrap",
                  }}
                >
                  {work.publication_year && <span>Year: {work.publication_year}</span>}
                  {work.work_type && <span style={{ textTransform: "capitalize" }}>Type: {work.work_type}</span>}
                  {work.author_position && <span>Position: {work.author_position} author</span>}
                  <span>Citations: {work.cited_by_count}</span>
                  {work.doi && (
                    <a
                      href={`https://doi.org/${work.doi}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      style={{ color: "var(--accent-blue)", display: "flex", alignItems: "center", gap: "3px" }}
                    >
                      <FileText size={12} /> DOI
                    </a>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
