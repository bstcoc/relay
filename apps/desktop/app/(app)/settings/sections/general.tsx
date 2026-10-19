"use client";

import { Button } from "@relay/ui/components/button";
import { Input } from "@relay/ui/components/input";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { manages, removePicture, supabase, type Team, uploadPicture, useAccount, useTeam } from "../../../account";
import { usePreferences } from "../../../preferences";
import { ConfirmDialog, Field, Panel, Picker, PicturePicker, TeamAvatar } from "../../../components/ui";
import { CopyValue, Group, INPUT, SaveBar, SELECT, Setting, useSave } from "./common";
import { type Member, teamMembers } from "./members";

export function General() {
  const { t } = usePreferences();
  const { refresh } = useAccount();
  const team = useTeam();
  const saved = team?.name ?? "";
  const [name, setName] = useState(saved);
  const [error, setError] = useState("");
  useEffect(() => setName(saved), [saved]);
  const admin = manages(team);

  const status = useSave();

  async function rename() {
    if (team) {
      await status.save(() => supabase.from("teams").update({ name: name.trim() }).eq("id", team.id), refresh);
    }
  }

  async function picture(file: File | null) {
    if (!team) {
      return;
    }
    setError("");
    try {
      const path = file ? await uploadPicture(`teams/${team.id}`, file) : null;
      const { error: refused } = await supabase.rpc("set_team_avatar", { team: team.id, path });
      if (refused) {
        throw refused;
      }
      if (team.path) {
        await removePicture(team.path).catch(() => undefined);
      }
      await refresh();
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : String(failure));
    }
  }

  return (
    <>
      <Group caption={!admin && t.settings.adminsOnly}
        footer={<SaveBar status={status} dirty={name !== saved} valid={!!name.trim()}
          onCancel={() => setName(saved)} onSave={() => void rename()} />}>
        <Setting label={t.settings.teamAvatar}
          help={error ? <span className="text-danger">{error}</span> : t.settings.teamAvatarHint}>
          {team && (
            <PicturePicker editable={admin} label={t.settings.changePicture} removeLabel={t.settings.removePicture}
              avatar={<TeamAvatar id={team.id} picture={team.picture} large />}
              onPick={(file) => picture(file)} onRemove={team.path ? () => picture(null) : undefined} />
          )}
        </Setting>
        <Setting label={t.settings.teamName} help={t.settings.teamNameHint}>
          <Input className={INPUT} maxLength={64} value={name} disabled={!admin}
            aria-label={t.settings.teamName} onChange={(e) => setName(e.target.value)} />
        </Setting>
        <Setting label={t.settings.teamId} help={t.settings.teamIdBody}>
          <CopyValue value={team?.id ?? ""} />
        </Setting>
      </Group>
      {team?.role === "owner" && <DangerZone team={team} />}
    </>
  );
}

function DangerZone({ team }: { team: Team }) {
  const { t } = usePreferences();
  const { account, refresh } = useAccount();
  const router = useRouter();
  const me = account.state === "signed-in" ? account.session.user.id : "";
  const [others, setOthers] = useState<Member[]>([]);
  const [heir, setHeir] = useState("");
  const [dialog, setDialog] = useState<"transfer" | "delete" | null>(null);
  const [typed, setTyped] = useState("");
  const [error, setError] = useState("");
  const chosen = others.find((m) => m.id === heir);

  useEffect(() => {
    void teamMembers(team.id).then(({ members }) => setOthers(members.filter((m) => m.id !== me)));
  }, [team.id, me]);

  function open(next: "transfer" | "delete") {
    setError("");
    setTyped("");
    setDialog(next);
  }

  async function transfer() {
    const { error: refused } = await supabase.rpc("transfer_ownership", { team: team.id, member: heir });
    if (refused) {
      setError(t.settings.transferFailed);
      return;
    }
    setDialog(null);
    await refresh();
  }

  async function remove() {
    const { error: refused } = await supabase.rpc("delete_team", { team: team.id });
    if (refused) {
      setError(t.settings.deleteFailed);
      return;
    }
    setDialog(null);
    await refresh();
    router.replace("/");
  }

  return (
    <>
      <Panel title={t.settings.transferTitle} description={t.settings.transferBody}
        hint={others.length === 0 && t.settings.transferNobody}
        action={<Button size="sm" variant="outline" disabled={!chosen}
          onClick={() => open("transfer")}>{t.settings.transferTitle}</Button>}>
        {others.length > 0 && (
          <Picker size="sm" className={SELECT} label={t.settings.newOwner} placeholder={t.settings.newOwner} value={heir}
            options={others.map((m) => ({ value: m.id, label: m.name }))} onChange={setHeir} />
        )}
      </Panel>
      <Panel title={t.settings.deleteTeam} description={t.settings.deleteTeamBody}
        action={<Button size="sm" variant="destructive"
          onClick={() => open("delete")}>{t.settings.deleteTeam}</Button>} />
      {dialog === "transfer" && chosen && (
        <ConfirmDialog title={t.settings.transferConfirmTitle(chosen.name)} body={t.settings.transferConfirmBody}
          action={t.settings.transferTitle} error={error} onClose={() => setDialog(null)} onConfirm={transfer} />
      )}
      {dialog === "delete" && (
        <ConfirmDialog title={t.settings.deleteConfirmTitle(team.name)} body={t.settings.deleteTeamBody}
          action={t.settings.deleteTeam} ready={typed === team.name} error={error}
          onClose={() => setDialog(null)} onConfirm={remove}>
          <Field label={t.settings.deleteType(team.name)}>
            <Input autoFocus value={typed} autoComplete="off" spellCheck={false}
              onChange={(e) => setTyped(e.target.value)} />
          </Field>
        </ConfirmDialog>
      )}
    </>
  );
}
