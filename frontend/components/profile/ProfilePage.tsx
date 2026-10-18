"use client";

import { useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Pencil } from "lucide-react";
import type { ResearcherProfile } from "../../types/researcher";
import { academicStatusLabel } from "../../utils/personalization";
import { useSession } from "../auth/SessionProvider";
import { usePreferenceIntelligence, useResearcherProfile, useResearcherWorks, useResearchTopics } from "../recommendations/resources";
import { Button } from "../ui/Button/Button";
import { PageHeader } from "../ui/PageHeader/PageHeader";
import { ErrorState, SkeletonList } from "../ui/State/State";
import { CreateProfile } from "./CreateProfile";
import { Publications } from "./Publications";
import { PreferencesCard } from "./PreferencesCard";
import { ProfileSummary } from "./ProfileSummary";
import { ResearchTopics } from "./ResearchTopics";
import styles from "./Profile.module.css";

/**
 * Where the profile's old sections went (P0.4 → P6). Their links keep working: recommendations,
 * personalization and history now live on /recommendations; research interests are this page's
 * "Research topics".
 */
export function sectionDestination(section: string | null): string | null {
  if (section === "recommendations" || section === "personalization" || section === "history") return "/recommendations";
  if (section === "interests") return "/researcher#topics";
  if (section === "profile") return "/researcher";
  return null;
}

/**
 * P6 — /researcher (plan §12): the profile summary, publications, research topics (stated and
 * from publications) and the way to preferences. Four requests besides the shell's: the profile,
 * its publications (once linked to a scholarly record), the topics in them and the preferences.
 */
export function ProfilePage() {
  const { profileId: sessionProfileId, user, refresh } = useSession();
  const router = useRouter();
  const section = useSearchParams().get("section");
  const destination = sectionDestination(section);

  const [created, setCreated] = useState<ResearcherProfile | null>(null);
  const profileId = sessionProfileId ?? created?.id ?? null;
  const profile = useResearcherProfile(destination ? null : profileId);
  const [edited, setEdited] = useState<ResearcherProfile | null>(null);
  const current = edited ?? created ?? profile.data ?? null;
  const [editing, setEditing] = useState(false);
  const [topicsRefresh, setTopicsRefresh] = useState(0);

  const works = useResearcherWorks(current?.canonical_researcher_id ? current.id : null);
  const topics = useResearchTopics(current ? current.id : null, topicsRefresh);
  const preferences = usePreferenceIntelligence(current ? current.id : null);

  useEffect(() => {
    if (destination) router.replace(destination);
  }, [destination, router]);

  // The sections below the summary appear together, once their first answers are in, so none of
  // them moves another while the page loads (CLS); after that each shows its own reloads.
  const pending = (resource: { status: string }) => resource.status === "loading" || resource.status === "idle";
  const firstSettled = Boolean(current) && !pending(topics) && !pending(preferences) && (!current?.canonical_researcher_id || !pending(works));
  const [sectionsShown, setSectionsShown] = useState(false);
  useEffect(() => {
    if (firstSettled) setSectionsShown(true);
  }, [firstSettled]);
  const showSections = sectionsShown || firstSettled;

  if (destination) return <SkeletonList rows={3} label="Opening the page" />;

  if (!current) {
    if (profileId && (profile.status === "loading" || profile.status === "idle")) {
      return (
        <>
          <PageHeader title="Your profile" />
          <SkeletonList rows={4} lines={2} label="Loading your profile" />
        </>
      );
    }
    if (profileId && profile.status === "error" && profile.error?.kind !== "not-found") {
      return (
        <>
          <PageHeader title="Your profile" />
          <ErrorState headingLevel={2} title="Your profile could not be loaded" kind={profile.error?.kind === "network" ? "offline" : "failed"} onRetry={profile.retry} />
        </>
      );
    }
    return (
      <>
        <PageHeader title="Your profile" description="Set up your researcher profile to get recommendations matched to your research." />
        <CreateProfile
          email={user?.email}
          onCreated={(made) => {
            setCreated(made);
            void refresh();
          }}
        />
      </>
    );
  }

  const facts = [
    academicStatusLabel(current.academic_status),
    current.institution?.display_name ?? current.institution_name,
    current.department,
    current.institution?.country_code,
  ].filter(Boolean);

  return (
    <>
      <PageHeader
        eyebrow="Researcher profile"
        title={current.full_name}
        description={facts.length > 0 ? facts.join(" · ") : "Add your career stage and institution to your profile."}
        actions={
          !editing && (
            <Button variant="secondary" leadingIcon={<Pencil size={16} aria-hidden="true" />} onClick={() => setEditing(true)}>
              Edit profile
            </Button>
          )
        }
      />
      <div className={styles.layout}>
        <div className={styles.column}>
          <ProfileSummary
            profile={current}
            editing={editing}
            onEditing={setEditing}
            onSaved={(updated) => {
              setEdited(updated);
              // An edit changes what the topics are drawn from: work them out again now, as before P6.
              setTopicsRefresh((n) => n + 1);
            }}
          />
          {showSections ? (
            <ResearchTopics profile={current} topics={topics} preferences={preferences} onRecompute={() => setTopicsRefresh((n) => n + 1)} />
          ) : (
            <SkeletonList rows={4} lines={2} label="Loading your research topics, publications and preferences" />
          )}
        </div>
        {showSections && (
          <div className={styles.column}>
            <Publications profile={current} works={works} />
            <PreferencesCard preferences={preferences} />
          </div>
        )}
      </div>
    </>
  );
}
