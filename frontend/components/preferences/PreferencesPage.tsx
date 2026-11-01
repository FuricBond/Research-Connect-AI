"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { Check, RefreshCw, X } from "lucide-react";
import { useSession } from "../auth/SessionProvider";
import {
  bulkUpdateResearcherPreferences,
  createResearcherPreference,
  deleteResearcherPreference,
  fetchResearcherProfile,
  fetchStructuredResearcherPreferences,
  updateResearcherPreference,
} from "../../services/api";
import type {
  BulkPreferenceItem,
  PreferenceCategory,
  PreferenceState,
  PreferenceType,
  ResearcherProfile,
  StructuredPreferencesResponse,
} from "../../types/researcher";
import { Breadcrumb } from "../ui/Breadcrumb/Breadcrumb";
import { Button, IconButton } from "../ui/Button/Button";
import { Card } from "../ui/Card/Card";
import { Checkbox, Select, TextInput } from "../ui/Field/Field";
import { PageHeader, SectionHeader } from "../ui/PageHeader/PageHeader";
import { Alert, EmptyState, ErrorState, SkeletonList } from "../ui/State/State";
import { preferenceCategoryLabel } from "../../utils/personalization";
import styles from "./Preferences.module.css";

const CALL_TYPES = [
  { value: "CONFERENCE", label: "Conference" },
  { value: "WORKSHOP", label: "Workshop" },
  { value: "JOURNAL", label: "Journal" },
  { value: "CALL_FOR_PAPERS", label: "Call for papers" },
  { value: "SPECIAL_ISSUE", label: "Special issue" },
  { value: "FELLOWSHIP", label: "Fellowship" },
  { value: "GRANT", label: "Grant" },
  { value: "INTERNSHIP", label: "Internship" },
];

const DELIVERY_MODES = [
  { value: "ONLINE", label: "Online or remote" },
  { value: "OFFLINE", label: "In person" },
  { value: "HYBRID", label: "Hybrid" },
];

const REGIONS = ["North America", "Europe", "United Kingdom", "Asia-Pacific", "India", "Latin America", "Middle East & Africa"];

const CAREER_STAGES = [
  { value: "EARLY_CAREER", label: "Early career (under 5 years after the PhD)" },
  { value: "MID_CAREER", label: "Mid-career (5 to 15 years after the PhD)" },
  { value: "SENIOR", label: "Senior or principal investigator" },
];

const ACADEMIC_LEVELS = [
  { value: "UNDERGRADUATE", label: "Undergraduate" },
  { value: "POSTGRADUATE", label: "Postgraduate or master's" },
  { value: "PHD_STUDENT", label: "PhD student" },
  { value: "POSTDOC", label: "Postdoctoral researcher" },
  { value: "FACULTY", label: "Faculty or professor" },
  { value: "INDUSTRY_RESEARCHER", label: "Industry researcher" },
];

const CURRENCIES = ["USD", "EUR", "GBP", "INR"];

const STATE_WORDS: Record<PreferenceState, string> = { NEUTRAL: "Neutral", PREFERRED: "Preferred", EXCLUDED: "Excluded" };
const STATE_CLASS: Record<PreferenceState, string> = { NEUTRAL: styles.neutral, PREFERRED: styles.preferred, EXCLUDED: styles.excluded };

/** The server's text never reaches the screen: it is written for developers. */
const SAVE_FAILED = "That change could not be saved. Try again.";

/**
 * Research preferences (/researcher/preferences, audit FUNC-04): what a person wants from
 * recommendations, in three states. Neutral is the absence of a preference, not a dislike. Every
 * change is one request and the page stays where it is while it saves; only the first load shows
 * a placeholder, and removing or adding something moves focus to the field beside the list.
 */
export function PreferencesPage() {
  const { profileId } = useSession();
  const [profile, setProfile] = useState<ResearcherProfile | null>(null);
  const [prefs, setPrefs] = useState<StructuredPreferencesResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadFailed, setLoadFailed] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const loadedOnce = useRef(false);
  const topicField = useRef<HTMLInputElement>(null);
  const keywordField = useRef<HTMLInputElement>(null);
  const institutionField = useRef<HTMLInputElement>(null);
  const exclusionsHeading = useRef<HTMLHeadingElement>(null);
  const focusAfterSave = useRef<HTMLElement | null>(null);

  const [topic, setTopic] = useState("");
  const [topicType, setTopicType] = useState<PreferenceType>("PREFERRED");
  const [keyword, setKeyword] = useState("");
  const [institution, setInstitution] = useState("");
  const [institutionType, setInstitutionType] = useState<PreferenceType>("PREFERRED");

  const [fundingRequired, setFundingRequired] = useState(false);
  const [minFunding, setMinFunding] = useState("");
  const [currency, setCurrency] = useState("USD");
  const [academicLevel, setAcademicLevel] = useState("");
  const [careerStage, setCareerStage] = useState("");

  const load = useCallback(async () => {
    if (!loadedOnce.current) setLoading(true);
    setError(null);
    setLoadFailed(false);
    try {
      // The signed-in account's own profile; an account without one is asked to create it.
      let own: ResearcherProfile | null = null;
      if (profileId) {
        own = await fetchResearcherProfile(profileId);
        setProfile(own);
      }
      if (own) {
        const next = await fetchStructuredResearcherPreferences(own.id);
        setPrefs(next);
        setFundingRequired(next.funding.funding_required);
        setMinFunding(next.funding.min_funding_amount ? String(next.funding.min_funding_amount) : "");
        setCurrency(next.funding.currency || "USD");
        setAcademicLevel(next.academic.academic_level || "");
        setCareerStage(next.academic.career_stage || "");
      }
    } catch {
      if (loadedOnce.current) setError("Your preferences could not be reloaded. What you see may be out of date.");
      else setLoadFailed(true);
    } finally {
      loadedOnce.current = true;
      setLoading(false);
    }
  }, [profileId]);

  useEffect(() => {
    void load();
  }, [load]);

  // The fields are held while saving: focus moves once they are not.
  useEffect(() => {
    if (saving || !focusAfterSave.current) return;
    focusAfterSave.current.focus();
    focusAfterSave.current = null;
  }, [saving]);

  const items = prefs?.raw_preferences ?? [];

  /** One change at a time: saves, reloads, and reports in words. */
  const save = async (change: () => Promise<unknown>, done?: string, focus?: HTMLElement | null) => {
    if (saving) return false;
    setSaving(true);
    setNotice(null);
    setError(null);
    try {
      await change();
      if (focus !== undefined) focusAfterSave.current = focus;
      await load();
      if (done) setNotice(done);
      return true;
    } catch {
      setError(SAVE_FAILED);
      return false;
    } finally {
      setSaving(false);
    }
  };

  const stateOf = (category: PreferenceCategory, value: string): PreferenceState => {
    const item = items.find((p) => p.category === category && p.preference_value.toUpperCase() === value.toUpperCase() && p.is_active);
    if (!item) return "NEUTRAL";
    return item.preference_type === "EXCLUDED" ? "EXCLUDED" : "PREFERRED";
  };

  const add = (category: PreferenceCategory, key: string, value: string, label: string, type: PreferenceType) =>
    createResearcherPreference(
      (profile as ResearcherProfile).id,
      { category, preference_type: type, preference_key: key, preference_value: value, display_label: label, strength: 1.0, is_active: true },
      (profile as ResearcherProfile).user_id
    );

  /** Neutral, then Preferred, then Excluded, then Neutral again. */
  const cycle = (category: PreferenceCategory, key: string, value: string, label: string) => {
    if (!profile) return;
    const state = stateOf(category, value);
    const existing = items.find((p) => p.category === category && p.preference_value.toUpperCase() === value.toUpperCase());
    void save(async () => {
      if (state === "NEUTRAL") await add(category, key, value, label, "PREFERRED");
      else if (!existing) return;
      else if (state === "PREFERRED") await updateResearcherPreference(profile.id, existing.id, { preference_type: "EXCLUDED" }, profile.user_id);
      else await deleteResearcherPreference(profile.id, existing.id, profile.user_id);
    });
  };

  const remove = (id: string, focus: HTMLElement | null) => {
    if (!profile) return;
    void save(() => deleteResearcherPreference(profile.id, id, profile.user_id), undefined, focus);
  };

  const addTopic = async (event: FormEvent) => {
    event.preventDefault();
    const clean = topic.trim();
    if (!clean || !profile) return;
    const verb = topicType === "EXCLUDED" ? "excluded" : "preferred";
    if (await save(() => add("TOPIC", "topic", clean, clean, topicType), `Added “${clean}” as a ${verb} topic.`, topicField.current)) setTopic("");
  };

  const addKeyword = async (event: FormEvent) => {
    event.preventDefault();
    const clean = keyword.trim();
    if (!clean || !profile) return;
    if (await save(() => add("KEYWORD", "keyword", clean, clean, "PREFERRED"), `Added the keyword “${clean}”.`, keywordField.current)) setKeyword("");
  };

  const addInstitution = async (event: FormEvent) => {
    event.preventDefault();
    const clean = institution.trim();
    if (!clean || !profile) return;
    const verb = institutionType === "EXCLUDED" ? "excluded" : "preferred";
    if (await save(() => add("INSTITUTION", "institution", clean, clean, institutionType), `Added “${clean}” as a ${verb} institution.`, institutionField.current)) setInstitution("");
  };

  const toggleRegion = (region: string, matchId: string | undefined) => {
    if (!profile) return;
    if (matchId) void save(() => deleteResearcherPreference(profile.id, matchId, profile.user_id));
    else void save(() => add("REGION", "region", region, region, "PREFERRED"), `Added ${region} as a preferred region.`);
  };

  const saveFunding = () => {
    if (!profile) return;
    const shared = { preference_type: "PREFERRED" as const, strength: 1.0, is_active: true };
    const amount = minFunding.trim();
    const synced: BulkPreferenceItem[] = [
      { ...shared, category: "FUNDING", preference_key: "funding_required", preference_value: String(fundingRequired), display_label: fundingRequired ? "Funding required" : "Funding optional" },
      ...(amount ? [{ ...shared, category: "FUNDING" as const, preference_key: "min_amount", preference_value: amount, display_label: `Minimum funding: ${currency} ${amount}` }] : []),
      { ...shared, category: "FUNDING", preference_key: "currency", preference_value: currency, display_label: `Currency: ${currency}` },
      ...(academicLevel
        ? [{ ...shared, category: "ACADEMIC_LEVEL" as const, preference_key: "academic_level", preference_value: academicLevel, display_label: ACADEMIC_LEVELS.find((l) => l.value === academicLevel)?.label ?? academicLevel }]
        : []),
      ...(careerStage
        ? [{ ...shared, category: "CAREER_STAGE" as const, preference_key: "career_stage", preference_value: careerStage, display_label: CAREER_STAGES.find((s) => s.value === careerStage)?.label ?? careerStage }]
        : []),
    ];
    void save(() => bulkUpdateResearcherPreferences(profile.id, { preferences: synced, replace_existing: false }, profile.user_id), "Funding and career stage saved.");
  };

  const header = (
    <>
      <Breadcrumb items={[{ label: "Researcher profile", href: "/researcher" }]} current="Research preferences" />
      <PageHeader
        title="Research preferences"
        description="Tell us what you want to see. Recommendations favour what you prefer and leave out what you exclude."
        actions={
          prefs && (
            <>
              <span className={styles.completeness}>{prefs.completeness.percentage}% complete</span>
              <Button variant="secondary" leadingIcon={<RefreshCw size={16} aria-hidden="true" />} onClick={() => void load()} disabled={saving}>
                Reload
              </Button>
            </>
          )
        }
      />
    </>
  );

  if (loading) {
    return (
      <div className={styles.page}>
        {header}
        <SkeletonList rows={4} lines={3} label="Loading your research preferences" />
      </div>
    );
  }
  if (loadFailed) {
    return (
      <div className={styles.page}>
        {header}
        <ErrorState title="Your research preferences could not be loaded" headingLevel={2} onRetry={() => void load()} />
      </div>
    );
  }
  if (!profile) {
    return (
      <div className={styles.page}>
        {header}
        <EmptyState headingLevel={2} title="Set up your researcher profile first." description={<>Preferences belong to your <Link href="/researcher">researcher profile</Link>.</>} />
      </div>
    );
  }

  const exclusions = items.filter((p) => p.preference_type === "EXCLUDED" && p.is_active);

  return (
    <div className={styles.page}>
      {header}

      <p role="status" className="rc-visually-hidden">
        {notice}
      </p>
      {notice && (
        <Alert tone="success" className={styles.notice}>
          {notice}
        </Alert>
      )}
      {error && (
        <Alert tone="danger" announce>
          {error}
        </Alert>
      )}

      <dl className={styles.legend}>
        {(
          [
            ["PREFERRED", "you want this, and it counts in favour"],
            ["NEUTRAL", "no preference, which is not the same as a dislike"],
            ["EXCLUDED", "you do not want this, and it is filtered out"],
          ] as const
        ).map(([state, meaning]) => (
          <div key={state} className={styles.legendItem}>
            <dt className={`${styles.state} ${STATE_CLASS[state]}`}>{STATE_WORDS[state]}</dt>
            <dd>{meaning}</dd>
          </div>
        ))}
      </dl>

      <div className={styles.grid}>
        <Card as="section" aria-labelledby="preferences-types">
          <SectionHeader id="preferences-types" title="Kinds of opportunity" description="Choose one to move it from neutral to preferred, to excluded, and back to neutral." />
          <CycleList options={CALL_TYPES} stateOf={(value) => stateOf("OPPORTUNITY_TYPE", value)} onCycle={(value, label) => cycle("OPPORTUNITY_TYPE", "opportunity_type", value, label)} />
        </Card>

        <Card as="section" aria-labelledby="preferences-delivery">
          <SectionHeader id="preferences-delivery" title="How you take part" description="How you would like to attend conferences, workshops and calls." />
          <CycleList options={DELIVERY_MODES} stateOf={(value) => stateOf("DELIVERY_MODE", value)} onCycle={(value, label) => cycle("DELIVERY_MODE", "delivery_mode", value, label)} />
        </Card>

        <Card as="section" aria-labelledby="preferences-topics">
          <SectionHeader id="preferences-topics" title="Topics and keywords" description="Research areas you are after, and subjects you would rather not see." />
          <Tags
            items={items.filter((p) => p.category === "TOPIC" && p.is_active).map((p) => ({ id: p.id, name: p.display_label, excluded: p.preference_type === "EXCLUDED" }))}
            onRemove={(id) => remove(id, topicField.current)}
          />
          <form onSubmit={addTopic} className={styles.addRow}>
            <TextInput ref={topicField} label="Topic" className={styles.grow} value={topic} onChange={(event) => setTopic(event.target.value)} placeholder="reinforcement learning" />
            <TypeSelect label="Prefer or exclude this topic" value={topicType} onChange={setTopicType} />
            <Button type="submit" variant="secondary" disabled={saving || !topic.trim()}>
              Add topic
            </Button>
          </form>
          <Tags
            items={items.filter((p) => p.category === "KEYWORD" && p.is_active).map((p) => ({ id: p.id, name: p.preference_value, excluded: false }))}
            onRemove={(id) => remove(id, keywordField.current)}
          />
          <form onSubmit={addKeyword} className={styles.addRow}>
            <TextInput ref={keywordField} label="Keyword" className={styles.grow} value={keyword} onChange={(event) => setKeyword(event.target.value)} placeholder="graph neural networks" />
            <Button type="submit" variant="secondary" disabled={saving || !keyword.trim()}>
              Add keyword
            </Button>
          </form>
        </Card>

        <Card as="section" aria-labelledby="preferences-places">
          <SectionHeader id="preferences-places" title="Regions and institutions" description="Places you would like to work with. Choose a region to add or remove it." />
          <ul className={styles.regions}>
            {REGIONS.map((region) => {
              const match = items.find((p) => (p.category === "REGION" || p.category === "LOCATION") && p.preference_value.toLowerCase() === region.toLowerCase() && p.is_active);
              const excluded = match?.preference_type === "EXCLUDED";
              return (
                <li key={region}>
                  <button type="button" className={`${styles.region} ${match ? (excluded ? styles.excluded : styles.preferred) : ""}`} aria-pressed={Boolean(match)} onClick={() => toggleRegion(region, match?.id)}>
                    {match && (excluded ? <X size={14} aria-hidden="true" /> : <Check size={14} aria-hidden="true" />)}
                    {region}
                    {excluded && <span className="rc-visually-hidden"> (excluded)</span>}
                  </button>
                </li>
              );
            })}
          </ul>
          <Tags
            items={items.filter((p) => p.category === "INSTITUTION" && p.is_active).map((p) => ({ id: p.id, name: p.display_label, excluded: p.preference_type === "EXCLUDED" }))}
            onRemove={(id) => remove(id, institutionField.current)}
          />
          <form onSubmit={addInstitution} className={styles.addRow}>
            <TextInput ref={institutionField} label="Institution" className={styles.grow} value={institution} onChange={(event) => setInstitution(event.target.value)} />
            <TypeSelect label="Prefer or exclude this institution" value={institutionType} onChange={setInstitutionType} />
            <Button type="submit" variant="secondary" disabled={saving || !institution.trim()}>
              Add institution
            </Button>
          </form>
        </Card>

        <Card as="section" aria-labelledby="preferences-funding">
          <SectionHeader id="preferences-funding" title="Funding and career stage" description="What funding you need, and where you are in your career." />
          <div className={styles.form}>
            <Checkbox label="I need opportunities that come with funding" checked={fundingRequired} onChange={(event) => setFundingRequired(event.target.checked)} />
            <div className={styles.addRow}>
              <TextInput label="Minimum funding amount" type="number" className={styles.grow} value={minFunding} onChange={(event) => setMinFunding(event.target.value)} />
              <Select label="Currency" value={currency} onChange={(event) => setCurrency(event.target.value)}>
                {CURRENCIES.map((code) => (
                  <option key={code} value={code}>
                    {code}
                  </option>
                ))}
              </Select>
            </div>
            <Select label="Academic level" value={academicLevel} onChange={(event) => setAcademicLevel(event.target.value)}>
              <option value="">Not stated</option>
              {ACADEMIC_LEVELS.map((level) => (
                <option key={level.value} value={level.value}>
                  {level.label}
                </option>
              ))}
            </Select>
            <Select label="Career stage" value={careerStage} onChange={(event) => setCareerStage(event.target.value)}>
              <option value="">Not stated</option>
              {CAREER_STAGES.map((stage) => (
                <option key={stage.value} value={stage.value}>
                  {stage.label}
                </option>
              ))}
            </Select>
            <div>
              <Button variant="primary" onClick={saveFunding} loading={saving}>
                Save funding and career stage
              </Button>
            </div>
          </div>
        </Card>

        <Card as="section" aria-labelledby="preferences-exclusions">
          <SectionHeader as="h2" id="preferences-exclusions" title={<span ref={exclusionsHeading} tabIndex={-1}>What you excluded</span>} description="These are left out of what you discover. Removing one sets it back to neutral." />
          {exclusions.length > 0 ? (
            <ul className={styles.exclusions}>
              {exclusions.map((item) => (
                <li key={item.id} className={styles.exclusion}>
                  <span>
                    <span className={styles.category}>{preferenceCategoryLabel(item.category)}:</span> {item.display_label}
                  </span>
                  <IconButton variant="ghost" size="sm" label={`Set ${item.display_label} back to neutral`} icon={<X size={16} aria-hidden="true" />} onClick={() => remove(item.id, exclusionsHeading.current)} />
                </li>
              ))}
            </ul>
          ) : (
            <p className={styles.none}>Nothing excluded. Everything you have not chosen stays neutral.</p>
          )}
        </Card>
      </div>
    </div>
  );
}

function CycleList({ options, stateOf, onCycle }: { options: { value: string; label: string }[]; stateOf: (value: string) => PreferenceState; onCycle: (value: string, label: string) => void }) {
  return (
    <ul className={styles.cycleList}>
      {options.map((option) => {
        const state = stateOf(option.value);
        return (
          <li key={option.value}>
            <button type="button" className={`${styles.cycle} ${STATE_CLASS[state]}`} onClick={() => onCycle(option.value, option.label)}>
              <span>{option.label}</span> <span className={styles.state}>{STATE_WORDS[state]}</span>
            </button>
          </li>
        );
      })}
    </ul>
  );
}

function Tags({ items, onRemove }: { items: { id: string; name: string; excluded: boolean }[]; onRemove: (id: string) => void }) {
  if (items.length === 0) return null;
  return (
    <ul className={styles.tags}>
      {items.map((item) => (
        <li key={item.id} className={`${styles.tag} ${item.excluded ? styles.excluded : ""}`}>
          {item.excluded && <span className={styles.tagState}>Excluded:</span>}
          {item.name}
          <button type="button" className={styles.tagRemove} aria-label={`Remove ${item.name}`} onClick={() => onRemove(item.id)}>
            <X size={14} aria-hidden="true" />
          </button>
        </li>
      ))}
    </ul>
  );
}

function TypeSelect({ label, value, onChange }: { label: string; value: PreferenceType; onChange: (value: PreferenceType) => void }) {
  return (
    <Select label={label} value={value} onChange={(event) => onChange(event.target.value as PreferenceType)}>
      <option value="PREFERRED">Prefer</option>
      <option value="EXCLUDED">Exclude</option>
    </Select>
  );
}
