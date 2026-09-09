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
          bar: "#0f766e",
          bg: "#f0fdf4",
          border: "#bbf7d0",
          text: "#166534",
        };
      case "INTERMEDIATE":
        return {
          bar: "#0284c7",
          bg: "#f0f9ff",
          border: "#bae6fd",
          text: "#0369a1",
        };
      case "BASIC":
        return {
          bar: "#d97706",
          bg: "#fffbeb",
          border: "#fde68a",
          text: "#92400e",
        };
      default:
        return {
          bar: "#64748b",
          bg: "#f8fafc",
          border: "#e2e8f0",
          text: "#475569",
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
              Profile Completeness: {completeness.percentage}% ({completeness.level})
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
          background: "#e2e8f0",
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
                <CheckCircle2 size={14} color="#16a34a" />
              ) : (
                <Circle size={14} color="#94a3b8" />
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
