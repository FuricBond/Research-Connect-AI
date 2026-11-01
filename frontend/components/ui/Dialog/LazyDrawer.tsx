"use client";

import { lazy, Suspense, type ComponentProps } from "react";

const Sheet = lazy(() => import("./Dialog").then((module) => ({ default: module.Drawer })));

/** A Drawer for a page that rarely opens one: its code loads the first time it does. */
export function Drawer(props: ComponentProps<typeof Sheet>) {
  if (!props.open) return null;
  return (
    <Suspense fallback={null}>
      <Sheet {...props} />
    </Suspense>
  );
}
