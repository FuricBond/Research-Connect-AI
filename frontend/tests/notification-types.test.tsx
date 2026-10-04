/**
 * Fix 4/9 — the frontend notification types match what the backend sends and accepts.
 *
 *  - The eight workspace collaboration types are notification types, each with its own icon,
 *    an accessible label, and (for a WORKSPACE source) a link to that workspace.
 *  - "WEEKS" is not an offset unit: the backend's check allows only DAYS, HOURS and MINUTES.
 */

import React from "react";
import { describe, expect, expectTypeOf, it, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn(), back: vi.fn(), forward: vi.fn(), refresh: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => "/notifications",
  useSearchParams: () => new URLSearchParams(),
}));

import NotificationsPageRoute from "../app/notifications/page";
import { SessionProvider } from "../components/auth/SessionProvider";
import { storeSession } from "../services/auth";
import type { NotificationItem, NotificationType, OffsetUnit } from "../types/notification";
import { PROFILE_ID, jsonResponse, makeTokenResponse, makeUser } from "./factories";

const WORKSPACE_ID = "ws000000-0000-4000-8000-000000000001";

const COLLABORATION: [NotificationType, string][] = [
  ["WORKSPACE_INVITATION", "Workspace invitation"],
  ["INVITATION_ACCEPTED", "Invitation accepted"],
  ["MEMBER_ROLE_CHANGED", "Role changed"],
  ["MEMBER_REMOVED", "Removed from workspace"],
  ["TASK_ASSIGNED", "Task assigned"],
  ["TASK_COMPLETED", "Task completed"],
  ["DOCUMENT_UPDATED", "Document updated"],
  ["COLLABORATION_ACTIVITY", "Workspace activity"],
];

function makeNotification(type: NotificationType, index: number): NotificationItem {
  return {
    id: `nt000000-0000-4000-8000-00000000000${index}`,
    profile_id: PROFILE_ID,
    notification_type: type,
    title: `${type} title`,
    body: "Something happened in your workspace.",
    source_type: "WORKSPACE",
    source_id: WORKSPACE_ID,
    scheduled_for: "2026-10-04T12:00:00+00:00",
    delivered_at: "2026-10-04T12:00:00+00:00",
    read_at: "2026-10-04T12:05:00+00:00",
    delivery_status: "DELIVERED",
    delivery_channel: "IN_APP",
    deduplication_key: `dedup-${index}`,
    metadata_json: { workspace_id: WORKSPACE_ID },
    created_at: "2026-10-04T12:00:00+00:00",
    updated_at: "2026-10-04T12:00:00+00:00",
  };
}

describe("notification types", () => {
  it("include the collaboration types and only the offset units the backend accepts", () => {
    expectTypeOf<"WORKSPACE_INVITATION">().toMatchTypeOf<NotificationType>();
    expectTypeOf<"INVITATION_ACCEPTED">().toMatchTypeOf<NotificationType>();
    expectTypeOf<"MEMBER_ROLE_CHANGED">().toMatchTypeOf<NotificationType>();
    expectTypeOf<"MEMBER_REMOVED">().toMatchTypeOf<NotificationType>();
    expectTypeOf<"TASK_ASSIGNED">().toMatchTypeOf<NotificationType>();
    expectTypeOf<"TASK_COMPLETED">().toMatchTypeOf<NotificationType>();
    expectTypeOf<"DOCUMENT_UPDATED">().toMatchTypeOf<NotificationType>();
    expectTypeOf<"COLLABORATION_ACTIVITY">().toMatchTypeOf<NotificationType>();
    expectTypeOf<OffsetUnit>().toEqualTypeOf<"MINUTES" | "HOURS" | "DAYS">();
    expectTypeOf<"WEEKS">().not.toMatchTypeOf<OffsetUnit>();
  });

  it("gives each collaboration notification its own labelled icon and a link to its workspace", async () => {
    const notifications = COLLABORATION.map(([type], index) => makeNotification(type, index));
    storeSession(makeTokenResponse({ user: makeUser({ role: "STUDENT" }) }));
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string) => {
        if (url.endsWith("/api/v1/auth/me")) return Promise.resolve(jsonResponse(makeUser({ role: "STUDENT" })));
        if (url.endsWith("/api/v1/notifications/unread-count")) {
          return Promise.resolve(jsonResponse({ profile_id: PROFILE_ID, unread_count: 0 }));
        }
        if (url.endsWith("/api/v1/notifications/delivery-status")) {
          return Promise.resolve(
            jsonResponse({
              in_app_enabled: true,
              email_enabled: true,
              email_delivery_available: false,
              reminders_scheduled: false,
              reminder_interval_seconds: null,
            })
          );
        }
        if (url.includes("/api/v1/notifications")) {
          return Promise.resolve(jsonResponse({ notifications, total: notifications.length, unread_count: 0 }));
        }
        return Promise.resolve(jsonResponse({ detail: `unexpected request ${url}` }, 404));
      })
    );

    render(
      <SessionProvider>
        <NotificationsPageRoute />
      </SessionProvider>
    );

    const icons = await Promise.all(COLLABORATION.map(([, label]) => screen.findByRole("img", { name: label })));
    // Every type has a distinct icon, never the generic bell.
    const shapes = icons.map((icon) => icon.querySelector("svg")?.getAttribute("class") ?? "");
    expect(new Set(shapes).size).toBe(COLLABORATION.length);
    expect(shapes.some((shape) => shape.includes("lucide-bell"))).toBe(false);

    for (const [type] of COLLABORATION) {
      const card = screen.getByText(`${type} title`).closest(".notification-card") as HTMLElement;
      expect(within(card).getByRole("link", { name: "Open workspace" })).toHaveAttribute(
        "href",
        `/workspace/${WORKSPACE_ID}`
      );
    }
  });
});
