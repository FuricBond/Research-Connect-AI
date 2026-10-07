"use client";

import React, { useState } from "react";
import { CheckCircle2, Circle, ChevronDown, ChevronUp, ShieldCheck } from "lucide-react";
import type { ProfileCompleteness } from "../../types/researcher";

interface ProfileCompletenessBadgeProps {
  completeness: ProfileCompleteness;
}

const FIELD_LABELS: Record<string, string> = {
  full_name: "Full Display Name",
  email: "Verified Email Identity",
  academic_status: "Academic Stage / Status",
  institution: "Institutional Affiliation",
  department: "Academic Department",
  bio: "Research Bio / Focus",
  external_identity: "External ID (ORCID / OpenAlex)",
  keywords: "Research Keywords",
};

export function ProfileCompletenessBadge({ completeness }: ProfileCompletenessBadgeProps) {
  const [expanded, setExpanded] = useState(false);

  const getTierColor = () => {
    switch (completeness.level) {
      case "COMPLETE":
        return {
          bar: "var(--rc-brand)",
          bg: "var(--rc-success-subtle)",
          border: "var(--rc-success-border)",
          text: "var(--rc-success)",
        };
      case "INTERMEDIATE":
        return {
          bar: "var(--rc-brand)",
          bg: "var(--rc-info-subtle)",
          border: "var(--rc-info-border)",
          text: "var(--rc-info)",
        };
      case "BASIC":
        return {
          bar: "var(--rc-warning)",
          bg: "var(--rc-warning-subtle)",
          border: "var(--rc-warning-border)",
          text: "var(--rc-warning)",
        };
      default:
        return {
          bar: "var(--rc-text-muted)",
          bg: "var(--rc-bg)",
          border: "var(--rc-border)",
          text: "var(--rc-text-secondary)",
        };
    }
  };

  const style = getTierColor();

  return (
    <div
      style={{
        background: style.bg,
        border: `1px solid ${style.border}`,
        borderRadius: "var(--radius-md)",
        padding: "16px 20px",
        marginBottom: "20px",
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          cursor: "pointer",
        }}
        onClick={() => setExpanded(!expanded)}
      >
        <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
          <ShieldCheck size={20} color={style.bar} />
          <div>
            <div style={{ fontWeight: 600, fontSize: "14px", color: style.text }}>
              Profile completeness: {completeness.percentage}% ({completeness.level.toLowerCase()})
            </div>
            <div style={{ fontSize: "12px", color: "var(--text-muted)" }}>
              Data foundation status for future personalized academic discovery
            </div>
          </div>
        </div>

        <button
          type="button"
          aria-label="Toggle profile completeness breakdown"
          style={{
            background: "none",
            border: "none",
            cursor: "pointer",
            color: style.text,
            display: "flex",
            alignItems: "center",
            gap: "4px",
            fontSize: "12px",
            fontWeight: 500,
          }}
        >
          {expanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
        </button>
      </div>

      {/* Progress bar */}
      <div
        style={{
          height: "6px",
          width: "100%",
          background: "var(--rc-border)",
          borderRadius: "9999px",
          marginTop: "12px",
          overflow: "hidden",
        }}
      >
        <div
          style={{
            width: `${completeness.percentage}%`,
            height: "100%",
            background: style.bar,
            transition: "width 0.4s ease",
          }}
        />
      </div>

      {/* Expandable Field Breakdown */}
      {expanded && (
        <div
          style={{
            marginTop: "14px",
            paddingTop: "12px",
            borderTop: `1px solid ${style.border}`,
            display: "grid",
            gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))",
            gap: "8px",
          }}
        >
          {Object.entries(completeness.field_breakdown).map(([field, present]) => (
            <div
              key={field}
              style={{
                display: "flex",
                alignItems: "center",
                gap: "8px",
                fontSize: "12px",
                color: present ? "var(--text-main)" : "var(--text-muted)",
              }}
            >
              {present ? (
                <CheckCircle2 size={14} color="var(--rc-success)" />
              ) : (
                <Circle size={14} color="var(--rc-text-muted)" />
              )}
              <span style={{ textDecoration: present ? "none" : "none" }}>
                {FIELD_LABELS[field] || field}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
