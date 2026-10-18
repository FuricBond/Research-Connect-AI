"use client";

import { useEffect, useState } from "react";
import { Plus, X } from "lucide-react";
import type { WorkspaceItem, WorkspaceItemUpdatePayload, WorkspacePriority } from "../../types/workspace";
import { Button, IconButton } from "../ui/Button/Button";
import { Select, TextArea, TextInput } from "../ui/Field/Field";
import styles from "./Workspace.module.css";

const PRIORITIES: { value: WorkspacePriority; label: string }[] = [
  { value: "LOW", label: "Low" },
  { value: "MEDIUM", label: "Medium" },
  { value: "HIGH", label: "High" },
  { value: "URGENT", label: "Urgent" },
];

interface ItemNotesFormProps {
  item: WorkspaceItem;
  /** The call's title, to name the tag list for screen readers. */
  title: string;
  saving: boolean;
  onUpdate: (item: WorkspaceItem, payload: WorkspaceItemUpdatePayload) => Promise<boolean>;
}

/**
 * Notes, tags and priority of a tracked call (plan §13: notes behind a disclosure, tags as chips).
 * Each change is saved on its own and replaced by the server's answer; a failure says so and
 * keeps what was typed. Used in the list rows and on the item's Overview.
 */
export function ItemNotesForm({ item, title, saving, onUpdate }: ItemNotesFormProps) {
  const [notes, setNotes] = useState(item.notes ?? "");
  const [tag, setTag] = useState("");
  const [message, setMessage] = useState("");

  // A newer server copy (another tab, a reload) replaces the draft only while nothing is typed.
  const serverNotes = item.notes ?? "";
  useEffect(() => {
    setNotes((current) => (current === "" ? serverNotes : current));
  }, [serverNotes]);

  const save = async (payload: WorkspaceItemUpdatePayload, done: string) => {
    const ok = await onUpdate(item, payload);
    setMessage(ok ? done : "That change could not be saved. Try again.");
    return ok;
  };

  const addTag = async () => {
    const value = tag.trim();
    if (!value || item.tags.includes(value)) {
      setTag("");
      return;
    }
    if (await save({ tags: [...item.tags, value] }, `Added the tag ${value}.`)) setTag("");
  };

  return (
    <div className={styles.rowDetailsBody}>
      <form
        className={styles.inlineForm}
        onSubmit={(event) => {
          event.preventDefault();
          void save({ notes }, "Notes saved.");
        }}
      >
        <TextArea label={<>Notes<span className="rc-visually-hidden"> for {title}</span></>} rows={3} value={notes} onChange={(event) => setNotes(event.target.value)} hint="Submission track, manuscript title, co-author tasks, reminders." />
        <div>
          <Button type="submit" variant="secondary" size="sm" disabled={saving || notes === serverNotes}>
            Save notes
          </Button>
        </div>
      </form>

      <div className={styles.tags}>
        {item.tags.length > 0 && (
          <ul className={styles.tagList} aria-label={`Tags on ${title}`}>
            {item.tags.map((value) => (
              <li key={value} className={styles.tag}>
                {value}
                <IconButton
                  size="sm"
                  label={`Remove tag ${value}`}
                  icon={<X size={14} aria-hidden="true" />}
                  disabled={saving}
                  onClick={() => void save({ tags: item.tags.filter((entry) => entry !== value) }, `Removed the tag ${value}.`)}
                />
              </li>
            ))}
          </ul>
        )}
        <form
          className={styles.tagForm}
          onSubmit={(event) => {
            event.preventDefault();
            void addTag();
          }}
        >
          <TextInput label={<>Add a tag<span className="rc-visually-hidden"> to {title}</span></>} value={tag} onChange={(event) => setTag(event.target.value)} maxLength={50} />
          <IconButton type="submit" variant="secondary" size="sm" label="Add tag" icon={<Plus size={16} aria-hidden="true" />} disabled={saving || !tag.trim()} />
        </form>
      </div>

      <Select
        label={
          <>
            Priority<span className="rc-visually-hidden"> for {title}</span>
          </>
        }
        value={item.priority}
        disabled={saving}
        onChange={(event) => {
          const value = event.target.value as WorkspacePriority;
          void save({ priority: value }, `Priority set to ${value.toLowerCase()}.`);
        }}
      >
        {PRIORITIES.map((priority) => (
          <option key={priority.value} value={priority.value}>
            {priority.label}
          </option>
        ))}
      </Select>
      <p role="status" className={styles.notice}>
        {message}
      </p>
    </div>
  );
}
