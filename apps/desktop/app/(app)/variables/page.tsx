"use client";

import { Braces } from "lucide-react";
import { usePreferences } from "../../preferences";
import { Empty } from "../../components/ui";
import { Page } from "../../shell";

export default function Variables() {
  const { t } = usePreferences();
  return (
    <Page title={t.variables.title}>
      <Empty icon={<Braces size={16} />} title={t.empty.variablesTitle}
        body={<>{t.empty.variablesBody} <code className="mono">{"${PGHOST}"}</code></>} />
    </Page>
  );
}
