import { EmptyState } from "../ui/State/State";
import { DashboardModule } from "./Module";

/** A legacy account without a researcher profile: the profile-based modules say why they are empty. */
export function NoProfile({ id, title }: { id: string; title: string }) {
  return (
    <DashboardModule id={id} title={title} reserve="timeline">
      <EmptyState bare headingLevel={3} title="This needs a researcher profile." description="Your account has no researcher profile yet." />
    </DashboardModule>
  );
}
