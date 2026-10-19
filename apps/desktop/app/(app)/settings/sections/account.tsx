"use client";

import { Input } from "@relay/ui/components/input";
import { useEffect, useState } from "react";
import { removePicture, supabase, uploadPicture, useAccount } from "../../../account";
import { type Theme, usePreferences } from "../../../preferences";
import { PicturePicker, Picker, UserAvatar } from "../../../components/ui";
import { Group, INPUT, SaveBar, SELECT, Setting, SignInFirst, useSave } from "./common";

export function Account() {
  const { t, language, setLanguage, theme, setTheme } = usePreferences();
  const { account, refresh } = useAccount();
  const saved = account.state === "signed-in" ? account.name : "";
  const [name, setName] = useState(saved);
  const [error, setError] = useState("");
  const status = useSave();
  useEffect(() => setName(saved), [saved]);
  if (account.state !== "signed-in") {
    return <SignInFirst />;
  }
  const id = account.session.user.id;
  async function rename() {
    await status.save(() => supabase.from("profiles").update({ display_name: name.trim() }).eq("user_id", id), refresh);
  }
  const previous = account.avatarPath;
  async function picture(file: File | null) {
    setError("");
    try {
      const path = file ? await uploadPicture(`users/${id}`, file) : null;
      const { error: refused } = await supabase.rpc("set_avatar", { path });
      if (refused) {
        throw refused;
      }
      if (previous) {
        await removePicture(previous).catch(() => undefined);
      }
      await refresh();
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : String(failure));
    }
  }
  return (
    <>
      <Group footer={<SaveBar status={status} dirty={name !== saved} valid={!!name.trim()}
        onCancel={() => setName(saved)} onSave={() => void rename()} />}>
        <Setting label={t.settings.avatar} help={error ? <span className="text-danger">{error}</span> : t.settings.avatarHint}>
          <PicturePicker editable label={t.settings.changePicture} removeLabel={t.settings.removePicture}
            avatar={<UserAvatar name={saved} picture={account.avatar} large />}
            onPick={(file) => picture(file)} onRemove={previous ? () => picture(null) : undefined} />
        </Setting>
        <Setting label={t.settings.displayName} help={t.settings.displayNameBody}>
          <Input className={INPUT} maxLength={32} value={name}
            aria-label={t.settings.displayName} onChange={(e) => setName(e.target.value)} />
        </Setting>
        <Setting label={t.settings.email}>
          <span className="truncate text-sm">{account.email}</span>
        </Setting>
      </Group>
      <Group title={t.settings.preferences}>
        <Setting label={t.user.language} help={t.settings.languageBody}>
          <Picker className={SELECT} label={t.user.language} value={language}
            options={[{ value: "fr", label: "Français" }, { value: "en", label: "English" }]}
            onChange={setLanguage} />
        </Setting>
        <Setting label={t.user.theme}>
          <Picker<Theme> className={SELECT} label={t.user.theme} value={theme}
            options={[
              { value: "system", label: t.user.system },
              { value: "light", label: t.user.light },
              { value: "dark", label: t.user.dark },
            ]}
            onChange={setTheme} />
        </Setting>
      </Group>
    </>
  );
}
