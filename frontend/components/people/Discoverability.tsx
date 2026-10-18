"use client";

import { useState } from "react";
import { updateDiscoverySettings } from "../../services/api";
import type { CollaborationInterest, CollaborationStatus, DiscoverySettings, DiscoverySettingsUpdate } from "../../types/peer";
import { ALL_COLLABORATION_INTERESTS, ALL_COLLABORATION_STATUSES, COLLABORATION_INTEREST_LABELS, COLLABORATION_STATUS_LABELS } from "../../types/peer";
import { Button } from "../ui/Button/Button";
import { Checkbox, Select, Switch, TextInput } from "../ui/Field/Field";
import styles from "./People.module.css";

/**
 * Whether others can find this researcher (Phase 5.12, opt-in) and what they see. Each change is
 * saved as it is made; the date of the last change to discoverability is the record of consent.
 */
export function Discoverability({ profileId, settings, onSaved }: { profileId: string; settings: DiscoverySettings; onSaved: (settings: DiscoverySettings) => void }) {
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState("");
  const [note, setNote] = useState(settings.collaboration_note ?? "");

  async function save(changes: DiscoverySettingsUpdate, done: string) {
    setSaving(true);
    try {
      onSaved(await updateDiscoverySettings(profileId, changes));
      setNotice(done);
    } catch {
      setNotice("Your settings could not be saved. Try again.");
    } finally {
      setSaving(false);
    }
  }

  const toggleInterest = (interest: CollaborationInterest) => {
    const current = settings.collaboration_interests;
    const next = current.includes(interest) ? current.filter((value) => value !== interest) : [...current, interest];
    void save({ collaboration_interests: next }, "Saved the collaboration you will consider.");
  };

  return (
    <section className={styles.panel} aria-labelledby="discoverability-heading">
      <h2 id="discoverability-heading" className={styles.panelTitle}>
        Your discoverability
      </h2>
      <Switch
        label="Let other researchers find me"
        description={
          <>
            Off: you can still look for peers, but you do not appear in anyone&apos;s results.
            {settings.consent_updated_at && <> Last changed {new Date(settings.consent_updated_at).toLocaleDateString(undefined, { dateStyle: "medium" })}.</>}
          </>
        }
        stateLabels={["Discoverable", "Not discoverable"]}
        checked={settings.is_discoverable}
        disabled={saving}
        onChange={(value) => save({ is_discoverable: value }, value ? "You are discoverable." : "You are no longer discoverable.")}
      />
      <div className={styles.grid}>
        <Select
          label="Availability shown to others"
          value={settings.collaboration_status}
          disabled={saving}
          onChange={(event) => save({ collaboration_status: event.target.value as CollaborationStatus }, "Saved your availability.")}
        >
          {ALL_COLLABORATION_STATUSES.map((status) => (
            <option key={status} value={status}>
              {COLLABORATION_STATUS_LABELS[status]}
            </option>
          ))}
        </Select>
        <fieldset className={styles.fieldset}>
          <legend className={styles.legend}>What others may see</legend>
          <Checkbox
            label="My institution and department"
            checked={settings.show_institution}
            disabled={saving}
            onChange={(event) => save({ show_institution: event.target.checked }, event.target.checked ? "Your institution is shown." : "Your institution is hidden.")}
          />
          <Checkbox
            label="My email address"
            checked={settings.show_contact_email}
            disabled={saving}
            onChange={(event) => save({ show_contact_email: event.target.checked }, event.target.checked ? "Your email is shown." : "Your email is hidden.")}
          />
        </fieldset>
      </div>
      <fieldset className={styles.fieldset}>
        <legend className={styles.legend}>Collaboration I will consider</legend>
        <ul className={styles.chips}>
          {ALL_COLLABORATION_INTERESTS.map((interest) => {
            const active = settings.collaboration_interests.includes(interest);
            return (
              <li key={interest}>
                <Button variant={active ? "primary" : "secondary"} size="sm" aria-pressed={active} disabled={saving} onClick={() => toggleInterest(interest)}>
                  {COLLABORATION_INTEREST_LABELS[interest]}
                </Button>
              </li>
            );
          })}
        </ul>
      </fieldset>
      <form
        className={styles.grid}
        onSubmit={(event) => {
          event.preventDefault();
          const value = note.trim();
          if (value !== (settings.collaboration_note ?? "")) void save({ collaboration_note: value || null }, "Saved your note.");
        }}
      >
        <TextInput label="Note shown to others (optional)" hint="For example: looking for co-authors on retrieval evaluation." maxLength={1000} value={note} disabled={saving} onChange={(event) => setNote(event.target.value)} />
        <div>
          <Button type="submit" variant="secondary" size="sm" disabled={saving || note.trim() === (settings.collaboration_note ?? "")}>
            Save note
          </Button>
        </div>
      </form>
      <p role="status" className={styles.notice}>
        {notice}
      </p>
    </section>
  );
}
