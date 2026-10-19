"use client";

import type { ReactNode } from "react";
import { SETTINGS } from "../../components/sidebar";
import { useHash } from "../../hooks";
import { usePreferences } from "../../preferences";
import { Page } from "../../shell";
import { Account } from "./sections/account";
import { Activity } from "./sections/activity";
import { Engine } from "./sections/engine";
import { General } from "./sections/general";
import { Members } from "./sections/members";
import { Migrations } from "./sections/migrations";
import { Notifications } from "./sections/notifications";
import { Privacy } from "./sections/privacy";
import { Roles } from "./sections/roles";
import { Security } from "./sections/security";

const SECTIONS: Record<string, () => ReactNode> = {
  general: General,
  account: Account,
  members: Members,
  roles: Roles,
  migrations: Migrations,
  privacy: Privacy,
  notifications: Notifications,
  security: Security,
  activity: Activity,
  engine: Engine,
};

export default function Settings() {
  const { t } = usePreferences();
  const hash = useHash("general");
  const section = SETTINGS.includes(hash) ? hash : "general";
  const Section = SECTIONS[section] ?? General;
  const title = t.settings.sections[section] ?? t.settings.title;
  return (
    <Page title={title} narrow>
      <Section />
    </Page>
  );
}

