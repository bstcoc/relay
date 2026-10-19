"use client";

import { FingerprintPattern } from "lucide-react";
import { usePreferences } from "../../preferences";
import { AnonymizeByDefault } from "../../components/anonymization";
import { Empty } from "../../components/ui";
import { Page } from "../../shell";

export default function Anonymization() {
  const { t } = usePreferences();
  return (
    <Page title={t.anonymization.title}>
      <AnonymizeByDefault />
      <Empty icon={<FingerprintPattern size={16} />} title={t.empty.anonymizationTitle}
        body={t.empty.anonymizationBody} />
    </Page>
  );
}
