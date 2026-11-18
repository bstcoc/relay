"use client";

import { Document, Sections } from "../document";
import { useLanguage } from "../i18n";

export function Notice() {
  const { t } = useLanguage();
  return (
    <Document title={t.legal.title}>
      <Sections sections={t.legal.sections} />
    </Document>
  );
}

export function Terms() {
  const { t } = useLanguage();
  return (
    <Document title={t.terms.title} lead={t.terms.updated}>
      <Sections sections={t.terms.sections} />
    </Document>
  );
}

export function Privacy() {
  const { t } = useLanguage();
  return (
    <Document title={t.privacy.title} lead={t.privacy.updated}>
      <Sections sections={t.privacy.sections} />
    </Document>
  );
}
