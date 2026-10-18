"use client";

import { useEffect, useReducer, useState } from "react";
import { useAddressSearch } from "../../../hooks/useAddressSearch";
import { useApiResource } from "../../../hooks/useApiResource";
import { getWorkspaceMembers } from "../../../services/api";
import { isUuid } from "../../../utils/ids";
import { callTypeLabel, deliveryModeLabel } from "../../../utils/research";
import { workspaceRoleMeta, workspaceStatusMeta } from "../../../utils/status";
import { workspaceDeadline } from "../../../utils/workspace";
import { useSession } from "../../auth/SessionProvider";
import { DeadlineCountdown } from "../../research/DeadlineCountdown";
import { RiskIndicator } from "../../research/RiskIndicator";
import { PriorityLabel } from "../../ui/Badge/Badge";
import { Breadcrumb } from "../../ui/Breadcrumb/Breadcrumb";
import { Button, ButtonLink } from "../../ui/Button/Button";
import { PageHeader } from "../../ui/PageHeader/PageHeader";
import { Alert, ErrorState, Skeleton, SkeletonList } from "../../ui/State/State";
import { TabPanel, Tabs, tabId } from "../../ui/Tabs/Tabs";
import { StatusMenu } from "../StatusMenu";
import { itemHref } from "../WorkspaceRow";
import { abilities, roleOn } from "../workflow";
import { ActivityPanel, MembersPanel, SubmissionPanel, TasksPanel } from "./lazyTabs";
import { OverviewPanel } from "./OverviewPanel";
import { useWorkspaceItem } from "./useWorkspaceItem";
import styles from "./Item.module.css";

export const ITEM_TABS = [
  { id: "overview", label: "Overview" },
  { id: "tasks", label: "Tasks" },
  { id: "submission", label: "Submission" },
  { id: "members", label: "Members" },
  { id: "activity", label: "Activity" },
] as const;

export type ItemTab = (typeof ITEM_TABS)[number]["id"];

/** `?tab=` names the open tab; Overview is the default and is left out of the address. */
export function readItemTab(params: URLSearchParams): ItemTab {
  const tab = params.get("tab");
  // The old page had a separate Invitations tab; invitations are part of Members now.
  if (tab === "invitations") return "members";
  return ITEM_TABS.some((entry) => entry.id === tab) ? (tab as ItemTab) : "overview";
}

export function itemTabHref(id: string, tab: ItemTab): string {
  return itemHref(id, tab === "overview" ? undefined : tab);
}

const CRUMBS = [{ label: "Workspace", href: "/workspace" }];

/**
 * P7 — `/workspace/[id]` (plan §13): the tracked call with its status, deadline and venue risk,
 * then tabs for Overview, Tasks, Submission, Members and Activity. The tab is in the address
 * (`?tab=tasks`), so links, back and forward open it. A tab loads its data the first time it is
 * opened and then stays mounted (hidden), so switching back asks the server nothing.
 *
 * The item is read by id, so a collaborator sees an item shared with them. What the viewer may
 * change follows their role (owner, or their member role); the server still decides.
 */
export function ItemPage({ id }: { id: string }) {
  const valid = isUuid(id);
  const [params, go] = useAddressSearch();
  const tab = readItemTab(params);
  const [visited, setVisited] = useState<Set<ItemTab>>(() => new Set([tab]));
  // A change in one tab (a task, a member, a submission) adds to the activity feed; this asks an
  // already opened Activity tab to read it again.
  const [activityVersion, activityChanged] = useReducer((n: number) => n + 1, 0);
  const { user } = useSession();
  const { resource, item, saving, failed, announcement, changeStatus, update, retryFailed, dismissFailed, reload } = useWorkspaceItem(valid ? id : null);

  useEffect(() => {
    setVisited((current) => (current.has(tab) ? current : new Set(current).add(tab)));
  }, [tab]);

  // Opening a tab from inside another (Overview's "Draft submission") moves focus to that tab, as
  // the control that was used is hidden with its panel.
  const openTab = (next: ItemTab) => {
    go(itemTabHref(id, next));
    requestAnimationFrame(() => document.getElementById(tabId("item", next))?.focus());
  };

  const isOwner = Boolean(item && user && item.user_id === user.id);
  // Members are needed for the Members tab, for assigning tasks, and to know a collaborator's role.
  const needMembers = valid && item !== null && (visited.has("members") || visited.has("tasks") || !isOwner);
  const members = useApiResource(needMembers ? `workspace:${id}:members` : null, (signal) => getWorkspaceMembers(id, undefined, undefined, signal));
  const can = abilities(roleOn(item ?? undefined, user?.id, members.data?.items));

  const title = item?.opportunity?.title || "Untitled call";
  useEffect(() => {
    if (item) document.title = `${title} — Workspace — ResearchConnect AI`;
  }, [item, title]);

  if (!valid || resource.error?.kind === "not-found") {
    return (
      <>
        <Breadcrumb items={CRUMBS} current="Not found" />
        <ErrorState
          kind="not-found"
          headingLevel={1}
          title="This workspace item was not found"
          description="It may have been removed, or the link may be wrong."
          actions={<ButtonLink href="/workspace">Open your workspace</ButtonLink>}
        />
      </>
    );
  }
  if (resource.error?.kind === "forbidden") {
    return (
      <>
        <Breadcrumb items={CRUMBS} current="No access" />
        <ErrorState
          kind="permission"
          headingLevel={1}
          title="This workspace item is not shared with you"
          description="Ask its owner to invite you, or open your own workspace."
          actions={<ButtonLink href="/workspace">Open your workspace</ButtonLink>}
        />
      </>
    );
  }
  if (!item) {
    if (resource.status === "error") {
      return (
        <>
          <Breadcrumb items={CRUMBS} current="Workspace item" />
          <ErrorState headingLevel={1} title="This workspace item could not be loaded" kind={resource.error?.kind === "network" ? "offline" : "failed"} onRetry={reload} />
        </>
      );
    }
    return (
      <div className={styles.loading} aria-busy="true">
        <Skeleton width="12rem" height="1rem" />
        <Skeleton width="min(36rem, 100%)" height="2.25rem" />
        <SkeletonList rows={3} lines={2} label="Loading the workspace item" />
      </div>
    );
  }

  const opp = item.opportunity;
  const deadline = workspaceDeadline(opp);
  const facts = [opp?.opportunity_type ? callTypeLabel(opp.opportunity_type) : null, opp?.publisher || opp?.organizer, opp?.location, deliveryModeLabel(opp?.delivery_mode)].filter(Boolean);
  const shared = !isOwner && can.role !== null;

  return (
    <>
      <Breadcrumb items={CRUMBS} current={title} />
      <PageHeader
        title={title}
        description={facts.length > 0 ? facts.join(" · ") : undefined}
        actions={
          <div className={styles.headerControls}>
            <StatusMenu item={item} saving={saving} canChange={can.edit} onChange={(target) => void changeStatus(target)} />
            <PriorityLabel priority={item.priority} />
          </div>
        }
      />
      <div className={styles.signals}>
        {opp && <DeadlineCountdown deadline={deadline.deadline} daysRemaining={deadline.daysRemaining} status={deadline.status} urgencyTier={deadline.urgencyTier} />}
        {opp && <RiskIndicator level={opp.risk_explanation?.risk_level ?? null} isPredatory={opp.is_predatory_flag} />}
        {shared && <span className={styles.role}>Shared with you · {workspaceRoleMeta(can.role).label}</span>}
      </div>

      <p role="status" className="rc-visually-hidden">
        {announcement}
      </p>
      {failed && (
        <Alert
          tone="danger"
          announce
          title={`The status could not be changed to ${workspaceStatusMeta(failed).label.toLowerCase()}.`}
          action={
            <span className={styles.alertActions}>
              <Button size="sm" variant="secondary" onClick={retryFailed}>
                Try again
              </Button>
              <Button size="sm" variant="ghost" onClick={dismissFailed}>
                Dismiss
              </Button>
            </span>
          }
        >
          It is back to what the server last confirmed.
        </Alert>
      )}

      <Tabs label="Workspace item" idPrefix="item" tabs={ITEM_TABS} selected={tab} onSelect={(next) => go(itemTabHref(id, next as ItemTab))} className={styles.tabs} />
      {ITEM_TABS.map(({ id: tabKey }) =>
        visited.has(tabKey) || tabKey === tab ? (
          <TabPanel key={tabKey} idPrefix="item" id={tabKey} hidden={tabKey !== tab}>
            {tabKey === "overview" && <OverviewPanel item={item} can={can} saving={saving} onUpdate={update} onOpenTab={openTab} />}
            {tabKey === "tasks" && <TasksPanel workspaceId={id} can={can} userId={user?.id ?? null} members={members} onChanged={activityChanged} />}
            {tabKey === "submission" && <SubmissionPanel item={item} can={can} onWorkspaceChanged={reload} onChanged={activityChanged} />}
            {tabKey === "members" && <MembersPanel workspaceId={id} can={can} userId={user?.id ?? null} members={members} onChanged={activityChanged} />}
            {tabKey === "activity" && <ActivityPanel workspaceId={id} can={can} version={activityVersion} />}
          </TabPanel>
        ) : null
      )}
    </>
  );
}
