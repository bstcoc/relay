"use client";

import { Badge } from "@relay/ui/components/badge";
import { Button } from "@relay/ui/components/button";
import { Input } from "@relay/ui/components/input";
import { Tabs, TabsList, TabsTrigger } from "@relay/ui/components/tabs";
import { cn } from "@relay/ui/lib/utils";
import { Mail, PlusCircle, Users } from "lucide-react";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { GIVEN_ROLES, initials, inviteLink, manages, pictureUrl, type Role, supabase, useAccount, type Team } from "../../../account";
import { usePreferences } from "../../../preferences";
import { Menu } from "../../../components/menu";
import { Avatar, ConfirmDialog, Empty, Frame, Panel, Picker, ROW, ROWS, SkeletonRows, UserAvatar } from "../../../components/ui";
import { SignInFirst } from "./common";

const TAB = "h-auto flex-none rounded-none px-0 pt-2 pb-3 font-normal text-muted-foreground data-[state=active]:text-foreground group-data-[orientation=horizontal]/tabs:after:bottom-[-1px]";

const MEMBER = cn(ROW, "grid-cols-[24px_minmax(0,1fr)_minmax(120px,auto)_32px] whitespace-nowrap");

export type Member = { id: string; name: string; email: string; picture: string | null; role: Role };

type MemberRow = {
  user_id: string; display_name: string; avatar_url: string | null; avatar_path: string | null; email: string; role: Role;
};

export async function teamMembers(team: string) {
  const { data, error } = await supabase.rpc("team_members", { team });
  return {
    error,
    members: ((data ?? []) as MemberRow[]).map((row): Member => ({
      id: row.user_id,
      name: row.display_name || row.email,
      email: row.email,
      picture: pictureUrl(row.avatar_path) ?? row.avatar_url,
      role: row.role,
    })),
  };
}

type Invitation = { id: string; email: string; role: Role; expires_at: string };

const rosters = new Map<string, { members: Member[]; invitations: Invitation[] }>();

function useRoster(team: string) {
  const [members, setMembers] = useState<Member[] | null>(() => rosters.get(team)?.members ?? null);
  const [invitations, setInvitations] = useState<Invitation[]>(() => rosters.get(team)?.invitations ?? []);
  const [failure, setFailure] = useState("");
  const load = useCallback(async () => {
    const [rows, pending] = await Promise.all([
      teamMembers(team),
      supabase.from("invitations").select("id, email, role, expires_at").eq("team_id", team).is("accepted_at", null),
    ]);
    const refused = rows.error ?? pending.error;
    if (refused) {
      setFailure(refused.message);
      return;
    }
    setFailure("");
    const loaded = { members: rows.members, invitations: (pending.data ?? []) as Invitation[] };
    rosters.set(team, loaded);
    setMembers(loaded.members);
    setInvitations(loaded.invitations);
  }, [team]);
  useEffect(() => { void load(); }, [load]);
  return { members, setMembers, invitations, failure, load };
}

export function Members() {
  const { account } = useAccount();
  return account.state === "signed-in" && account.team
    ? <Roster team={account.team} me={account.session.user.id} />
    : <SignInFirst />;
}

function Roster({ team, me }: { team: Team; me: string }) {
  const { t } = usePreferences();
  const { refresh } = useAccount();
  const router = useRouter();
  const { members, setMembers, invitations, failure, load } = useRoster(team.id);
  const [lines, setLines] = useState([{ email: "", role: "member" }]);
  const [tab, setTab] = useState<"members" | "pending">("members");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [removing, setRemoving] = useState<Member | null>(null);
  const admin = manages(team);
  const filled = lines.filter((l) => l.email.includes("@"));

  async function invite() {
    setError("");
    for (const line of filled) {
      const result = await supabase.rpc("invite", { team: team.id, address: line.email, given: line.role });
      if (result.error) {
        setError(result.error.message);
        break;
      }
    }
    setLines([{ email: "", role: "member" }]);
    setTab("pending");
    await load();
  }

  async function setRole(member: Member, role: Role) {
    const before = members;
    setError("");
    setMembers(before?.map((m) => (m.id === member.id ? { ...m, role } : m)) ?? null);
    const result = await supabase.rpc("set_role", { team: team.id, member: member.id, given: role });
    if (result.error) {
      setMembers(before);
      setError(t.settings.roleFailed(member.name));
      return;
    }
    await load();
  }

  async function leave() {
    const result = await supabase.from("members").delete().eq("team_id", team.id).eq("user_id", me);
    if (result.error) {
      setError(t.settings.leaveFailed);
      return;
    }
    await refresh();
    router.replace("/");
  }

  async function act(change: PromiseLike<{ error: { message: string } | null }>) {
    const result = await change;
    setError(result.error?.message ?? "");
    await load();
  }

  return (
    <>
      {admin && (
        <Panel title={t.settings.invite} hint={t.settings.inviteHint}
          action={<Button size="sm" disabled={!filled.length} onClick={() => void invite()}>{t.settings.sendInvites}</Button>}>
          <div className="grid grid-cols-[minmax(0,1fr)_200px] gap-x-3 gap-y-2">
            <span className="text-muted-foreground">{t.settings.email}</span>
            <span className="text-muted-foreground">{t.settings.role}</span>
            {lines.map((line, index) => (
              <InviteLine key={index} line={line}
                onChange={(next) => setLines(lines.map((l, i) => (i === index ? next : l)))} />
            ))}
          </div>
          <div>
            <Button size="sm" variant="outline" onClick={() => setLines([...lines, { email: "", role: "member" }])}>
              <PlusCircle /> {t.settings.addLine}
            </Button>
          </div>
        </Panel>
      )}
      {error && <p className="text-sm text-danger">{error}</p>}
      {notice && <p className="text-sm text-muted-foreground">{notice}</p>}
      {admin ? (
        <Tabs value={tab} onValueChange={(next) => setTab(next as typeof tab)}>
          <TabsList variant="line" className="h-auto w-full justify-start gap-4 rounded-none border-b border-border p-0">
            <TabsTrigger value="members" className={TAB}>{t.settings.teamMembers}</TabsTrigger>
            <TabsTrigger value="pending" className={TAB}>{t.settings.pending}</TabsTrigger>
          </TabsList>
        </Tabs>
      ) : <h2 className="text-base font-semibold">{t.settings.teamMembers}</h2>}
      {failure ? <p className="text-sm text-danger">{failure}</p>
        : tab === "members" ? !members ? <SkeletonRows cells={[100, 30, 60]} count={1} />
        : members.length === 0 ? <Empty icon={<Users size={16} />} title={t.settings.noMembers} body={t.settings.noMembersBody} /> : (
        <Frame><ul className={ROWS}>
          {members.map((m) => (
            <li key={m.id} className={MEMBER}>
              <UserAvatar name={m.name} picture={m.picture} />
              <span className="flex min-w-0 flex-col">
                <span className="flex min-w-0 items-center gap-2 font-medium">
                  <span className="min-w-0 truncate" title={m.name}>{m.name}</span>
                  {m.id === me && <Badge variant="secondary" className="h-6 shrink-0">{t.settings.you}</Badge>}
                </span>
                {m.name !== m.email && <span className="truncate text-sm text-muted-foreground" title={m.email}>{m.email}</span>}
              </span>
              {admin && m.role !== "owner" && m.id !== me ? (
                <Picker size="sm" className="w-40" label={t.settings.roleOf(m.name)} value={m.role}
                  options={(GIVEN_ROLES.includes(m.role) ? GIVEN_ROLES : [...GIVEN_ROLES, m.role])
                    .map((value) => ({ value, label: t.settings.roles[value] }))}
                  onChange={(role) => void setRole(m, role)} />
              ) : <span className="text-muted-foreground">{t.settings.roles[m.role]}</span>}
              {m.role === "owner" || (m.id !== me && !admin) ? <span /> : (
                <Menu label={m.name} items={[
                  {
                    label: m.id === me ? t.settings.leave : t.settings.removeMember,
                    danger: true,
                    onSelect: () => setRemoving(m),
                  },
                ]} />
              )}
            </li>
          ))}
        </ul></Frame>
      ) : invitations.length ? (
        <Frame><ul className={ROWS}>
          {invitations.map((i) => ({ ...i, expired: new Date(i.expires_at) <= new Date() })).map((i) => (
            <li key={i.id} className={MEMBER}>
              <Avatar>{initials(i.email)}</Avatar>
              <span className="flex min-w-0 items-center gap-2 font-medium">
                <span className="min-w-0 truncate" title={i.email}>{i.email}</span>
                {i.expired && <Badge variant="secondary" className="h-6 shrink-0">{t.settings.expired}</Badge>}
              </span>
              <span className="text-muted-foreground">{t.settings.roles[i.role]}</span>
              <Menu label={i.email} items={[
                i.expired
                  ? { label: t.settings.resend, onSelect: () => void act(supabase.rpc("invite", { team: team.id, address: i.email, given: i.role })) }
                  : { label: t.settings.copyLink, onSelect: () => void navigator.clipboard.writeText(inviteLink(i.id))
                    .then(() => setNotice(t.settings.linkCopied(i.email))) },
                { label: t.settings.withdraw, danger: true, onSelect: () => void act(supabase.from("invitations").delete().eq("id", i.id)) },
              ]} />
            </li>
          ))}
        </ul></Frame>
      ) : (
        <Empty icon={<Mail size={16} />} title={t.settings.noPending} body={t.settings.noPendingBody} />
      )}
      {removing && (
        <ConfirmDialog
          title={removing.id === me ? t.settings.leaveTitle : t.settings.removeTitle(removing.name)}
          body={removing.id === me ? t.settings.leaveBody : t.settings.removeBody}
          action={removing.id === me ? t.settings.leave : t.settings.removeConfirm(removing.name)}
          onClose={() => setRemoving(null)}
          onConfirm={async () => {
            if (removing.id === me) {
              await leave();
            } else {
              await act(supabase.from("members").delete().eq("team_id", team.id).eq("user_id", removing.id));
            }
            setRemoving(null);
          }} />
      )}
    </>
  );
}

function InviteLine({ line, onChange }: {
  line: { email: string; role: string };
  onChange: (line: { email: string; role: string }) => void;
}) {
  const { t } = usePreferences();
  return (
    <>
      <Input type="email" placeholder="camille@example.com" value={line.email}
        aria-label={t.settings.email} onChange={(e) => onChange({ ...line, email: e.target.value })} />
      <Picker label={t.settings.role} value={line.role}
        options={GIVEN_ROLES.map((value) => ({ value, label: t.settings.roles[value] }))}
        onChange={(role) => onChange({ ...line, role })} />
    </>
  );
}
