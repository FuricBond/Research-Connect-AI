"use client";

import { forwardRef, useId, type ComponentProps } from "react";
import { Search, X } from "lucide-react";
import { cx } from "../../../utils/cx";
import { IconButton } from "../Button/Button";
import styles from "./Field.module.css";

type SearchInputProps = Omit<ComponentProps<"input">, "className" | "type"> & {
  /** The accessible name; shown as a visible label unless `hideLabel`. */
  label: string;
  hideLabel?: boolean;
  /** Shows one clear button while there is text. */
  onClear?: () => void;
  className?: string;
};

/** On its own so the header, on every page, does not carry the other fields. */
export const SearchInput = forwardRef<HTMLInputElement, SearchInputProps>(function SearchInput(
  { label, hideLabel, onClear, className, id, value, ...rest },
  ref
) {
  const generated = useId();
  const inputId = id ?? `search-${generated}`;
  const hasText = typeof value === "string" ? value.length > 0 : false;
  return (
    <div className={cx(styles.field, className)}>
      <label className={cx(styles.label, hideLabel && "rc-visually-hidden")} htmlFor={inputId}>
        {label}
      </label>
      <div className={styles.search}>
        <Search size={16} className={styles.searchIcon} aria-hidden="true" />
        <input ref={ref} id={inputId} type="search" className={cx(styles.control, styles.searchControl)} value={value} {...rest} />
        {onClear && hasText && (
          <IconButton className={styles.clear} size="sm" label="Clear search" icon={<X size={16} aria-hidden="true" />} onClick={onClear} />
        )}
      </div>
    </div>
  );
});
