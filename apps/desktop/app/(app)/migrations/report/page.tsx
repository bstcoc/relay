"use client";

import { Button } from "@relay/ui/components/button";
import Link from "next/link";
import { useEffect, useState } from "react";
import { canEdit, useTeam } from "../../../account";
import { get, type Migration } from "../../../migrations";
import { errorMessage } from "../../../engine";
import { usePreferences } from "../../../preferences";
import { SkeletonRows } from "../../../components/ui";
import { useHash } from "../../../hooks";
import { Page } from "../../../shell";
import { ReportView } from "../report-view";

export default function Report() {
  const { t } = usePreferences();
  const id = useHash("");
  const [migration, setMigration] = useState<Migration | null>(null);
  const [error, setError] = useState("");
  const editor = canEdit(useTeam());

  useEffect(() => {
    if (id) {
      get(id).then(setMigration).catch((failure: unknown) => setError(errorMessage(failure)));
    }
  }, [id]);

  return (
    <Page title={migration ? `${migration.source_name} → ${migration.target_name}` : t.migrations.title}
      actions={editor && migration?.source_id && migration.target_id ? (
        <Button asChild variant="outline">
          <Link href={`/migrations/new/#replay=${migration.id}`} className="no-underline">{t.wizard.replay}</Link>
        </Button>
      ) : null}>
      {error && <p className="text-sm text-danger">{error}</p>}
      {migration ? <ReportView migration={migration} /> : !error && <SkeletonRows cells={[30, 10]} />}
    </Page>
  );
}
