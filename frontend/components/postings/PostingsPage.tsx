"use client";

import { useCallback, useEffect, useState } from "react";
import { Plus } from "lucide-react";
import { useAddressSearch } from "../../hooks/useAddressSearch";
import { fetchPostingFits, fetchPostings } from "../../services/api";
import type { PostingFilterParams, PostingFit, PostingType, PostingWorkMode, ResearchPosting } from "../../types/posting";
import { POSTING_TYPE_LABELS, WORK_MODE_LABELS } from "../../types/posting";
import { NEW_POSTING_HREF } from "../../utils/postings";
import { RequireAuth } from "../auth/RequireAuth";
import { useSession } from "../auth/SessionProvider";
import { Button, ButtonLink } from "../ui/Button/Button";
import { Checkbox, SearchInput, Select } from "../ui/Field/Field";
import { PageHeader } from "../ui/PageHeader/PageHeader";
import { EmptyState, ErrorState, SkeletonList } from "../ui/State/State";
import { MyPostings } from "./lazy";
import { PostingCard } from "./PostingCard";
import { PostingsNav } from "./PostingsNav";
import { POSTING_TYPES, WORK_MODES } from "./postingForm";
import discover from "./PostingsPage.module.css";

/**
 * `/postings`: Discover for everyone (P6); `/postings?view=mine` is My postings, for the accounts
 * that may author postings (P9). Hiding the view from other roles is a convenience: the API only
 * ever returns a person's own postings there.
 */
export function PostingsPage() {
  const [params] = useAddressSearch();
  if (params.get("view") === "mine") {
    return (
      <RequireAuth roles={["FACULTY", "ADMIN"]}>
        <MyPostings />
      </RequireAuth>
    );
  }
  return <Discover />;
}

/**
 * Discover (P6): search (applied when submitted), category, work mode and "Accepting
 * applications"; for a signed-in student, one batch of fits once the list is in.
 */
function Discover() {
  const { status, hasRole } = useSession();
  const [postings, setPostings] = useState<ResearchPosting[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [loadFailed, setLoadFailed] = useState(false);

  const [searchInput, setSearchInput] = useState("");
  const [search, setSearch] = useState("");
  const [typeFilter, setTypeFilter] = useState<PostingType | "">("");
  const [workModeFilter, setWorkModeFilter] = useState<PostingWorkMode | "">("");
  const [acceptingOnly, setAcceptingOnly] = useState(false);

  // Authoring is a faculty/admin capability. The server enforces this regardless; the UI only
  // avoids offering an action that would certainly be refused.
  const isSignedIn = status === "authenticated";
  const canAuthor = isSignedIn && hasRole("FACULTY", "ADMIN");
  const isStudent = isSignedIn && hasRole("STUDENT");

  // Phase 5.15: a signed-in student's fit for each listed posting, by posting id.
  const [fits, setFits] = useState<Record<string, PostingFit>>({});

  const load = useCallback(async () => {
    setLoading(true);
    setLoadFailed(false);
    try {
      const filters: PostingFilterParams = {
        search: search.trim() || undefined,
        posting_type: typeFilter || undefined,
        work_mode: workModeFilter || undefined,
        accepting_only: acceptingOnly || undefined,
        limit: 50,
      };
      const listed = await fetchPostings(filters);
      setPostings(listed.postings);
      setTotal(listed.total);
    } catch {
      setLoadFailed(true);
      setPostings([]);
      setTotal(0);
    } finally {
      setLoading(false);
    }
  }, [search, typeFilter, workModeFilter, acceptingOnly]);

  useEffect(() => {
    load();
  }, [load]);

  // One batch call once the list is in. The list never waits on it, and a failure only means
  // the cards show no fit.
  useEffect(() => {
    if (!isStudent || postings.length === 0) {
      setFits({});
      return;
    }
    const controller = new AbortController();
    fetchPostingFits(
      postings.map((posting) => posting.id),
      controller.signal
    )
      .then((result) => {
        setFits(Object.fromEntries(result.fits.map((fit) => [fit.posting_id, fit])));
      })
      .catch(() => {
        // Fit is an extra; the postings stay listed without it.
      });
    return () => controller.abort();
  }, [isStudent, postings]);

  const filtered = Boolean(search || typeFilter || workModeFilter || acceptingOnly);

  return (
    <>
      <PageHeader
        title="Research postings"
        description="Projects, thesis topics, collaborations and positions posted by faculty on this platform, each with a named academic who is accountable for it."
        actions={
          canAuthor && (
            <ButtonLink href={NEW_POSTING_HREF} variant="primary" leadingIcon={<Plus size={16} aria-hidden="true" />}>
              New posting
            </ButtonLink>
          )
        }
      />
      <PostingsNav current="discover" />

      <form
        className={discover.filters}
        role="search"
        aria-label="Research postings"
        onSubmit={(event) => {
          event.preventDefault();
          setSearch(searchInput);
        }}
      >
        <div className={discover.searchRow}>
          <SearchInput
            label="Search postings"
            value={searchInput}
            onChange={(event) => setSearchInput(event.target.value)}
            onClear={() => {
              setSearchInput("");
              setSearch("");
            }}
          />
          <Button type="submit">Search</Button>
        </div>
        <div className={discover.filterRow}>
          <Select label="Category" value={typeFilter} onChange={(event) => setTypeFilter(event.target.value as PostingType | "")}>
            <option value="">All categories</option>
            {POSTING_TYPES.map((t) => (
              <option key={t} value={t}>
                {POSTING_TYPE_LABELS[t]}
              </option>
            ))}
          </Select>
          <Select label="Work mode" value={workModeFilter} onChange={(event) => setWorkModeFilter(event.target.value as PostingWorkMode | "")}>
            <option value="">Any work mode</option>
            {WORK_MODES.map((m) => (
              <option key={m} value={m}>
                {WORK_MODE_LABELS[m]}
              </option>
            ))}
          </Select>
          <Checkbox label="Accepting applications" checked={acceptingOnly} onChange={(event) => setAcceptingOnly(event.target.checked)} />
        </div>
      </form>

      <section className={discover.results} aria-labelledby="postings-results-heading" aria-busy={loading || undefined}>
        <h2 id="postings-results-heading" className={discover.resultsTitle}>
          Open postings
        </h2>
        {loading ? (
          <SkeletonList rows={3} lines={3} label="Loading research postings" />
        ) : loadFailed ? (
          <ErrorState title="Research postings could not be loaded" onRetry={load} />
        ) : postings.length === 0 ? (
          <EmptyState
            variant={filtered ? "no-results" : "first-use"}
            title="No open research postings match these filters."
            description="Try another category or work mode, or clear the search."
          />
        ) : (
          <>
            <p className={discover.count} role="status">
              {total} posting{total === 1 ? "" : "s"}
            </p>
            <ul className={discover.list}>
              {postings.map((posting) => (
                <li key={posting.id}>
                  <PostingCard posting={posting} fit={fits[posting.id] ?? null} />
                </li>
              ))}
            </ul>
          </>
        )}
      </section>
    </>
  );
}
