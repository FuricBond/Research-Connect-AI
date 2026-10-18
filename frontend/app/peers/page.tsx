"use client";

import { RequireAuth } from "../../components/auth/RequireAuth";
import { PeersPage } from "../../components/people/PeersPage";

/** /peers (P6): your discoverability and suggested peers. */
export default function PeerDiscoveryPageRoute() {
  return (
    <RequireAuth>
      <PeersPage />
    </RequireAuth>
  );
}
