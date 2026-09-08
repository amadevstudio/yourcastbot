import { FormEvent, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";
import { ChevronDown, ChevronUp, Search, X } from "lucide-react";
import { api, BotUser, Sub } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Badge, Card, Hint, Input, Skeleton } from "@/components/ui/primitives";

const SUB_PREVIEW = 8;

function SubChips({
  subs,
  expanded,
  onToggle,
  globalOpen,
}: {
  subs: Sub[];
  expanded: boolean;
  onToggle: () => void;
  globalOpen: boolean;
}) {
  const visible = expanded ? subs : subs.slice(0, SUB_PREVIEW);
  const hidden = Math.max(subs.length - SUB_PREVIEW, 0);
  if (!subs.length) {
    return <Hint>Подкастов в списке нет.</Hint>;
  }
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap gap-1">
        {visible.map((sub, index) => (
          <span
            key={`${sub.name}-${index}`}
            title={
              sub.notify
                ? "Notify включён — новые выпуски этого подкаста"
                : "Подкаст в списке, уведомления выключены"
            }
            className={`rounded px-2 py-1 text-xs text-black ${
              sub.notify ? "bg-brand" : "bg-yellow-200/80"
            }`}
          >
            {sub.name}
          </span>
        ))}
      </div>
      {hidden > 0 && !globalOpen ? (
        <button
          type="button"
          className="text-xs font-medium text-brand hover:underline"
          onClick={onToggle}
        >
          {expanded
            ? "Свернуть список подкастов"
            : `Показать все ${subs.length} · ещё ${hidden}`}
        </button>
      ) : null}
    </div>
  );
}

function UserCard({
  user,
  onFilter,
  defaultOpen,
  forceSubsOpen,
}: {
  user: BotUser;
  onFilter: (tgid: string) => void;
  defaultOpen: boolean;
  forceSubsOpen: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  const expanded = forceSubsOpen || open;
  const longList = user.subs.length > SUB_PREVIEW;
  return (
    <Card className="space-y-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="space-y-2">
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <button
              type="button"
              className="font-mono text-brand hover:underline"
              title="Показать только этого человека"
              onClick={() => onFilter(String(user.telegramId))}
            >
              #{user.id} · {user.telegramId}
            </button>
            <Badge>{user.lang || "язык не задан"}</Badge>
            {user.deleted ? <Badge tone="mute">заблокировал бота</Badge> : null}
            {user.receives_episodes ? (
              <Badge tone="warn">получает выпуски</Badge>
            ) : null}
            <span className="text-zinc-500">
              подкастов: {user.channels_count}
            </span>
          </div>
          <div className="text-xs text-zinc-400">
            Тариф {user.tariff_id ?? "нет"}
            {user.time_left_days != null
              ? ` · осталось ${user.time_left_days.toFixed(1)} дн.`
              : ""}
            {user.notify_count != null
              ? ` · лимит notify ${
                  user.notify_count === -1 ? "без ограничения" : user.notify_count
                }`
              : ""}
            {user.balance != null ? ` · баланс ${user.balance}` : ""}
          </div>
        </div>
        {!forceSubsOpen && (longList || user.receives_episodes) ? (
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => setOpen((v) => !v)}
          >
            {expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
            {expanded ? "Свернуть" : "Подробнее"}
          </Button>
        ) : null}
      </div>
      {expanded && user.receives_episodes ? (
        <Hint>
          Живой тариф и notify хотя бы на одном подкасте — бот шлёт этому
          человеку новые аудиовыпуски.
        </Hint>
      ) : null}
      <SubChips
        subs={user.subs}
        expanded={expanded}
        globalOpen={forceSubsOpen}
        onToggle={() => setOpen((v) => !v)}
      />
    </Card>
  );
}

export default function Users() {
  const [params, setParams] = useSearchParams();
  const page = Number(params.get("page") || "1");
  const tgid = params.get("tgid") || "";
  const [search, setSearch] = useState(tgid);
  const [expandAll, setExpandAll] = useState(false);
  const { data, isLoading } = useQuery({
    queryKey: ["users", page, tgid],
    queryFn: () => api.users(page, tgid || undefined),
  });

  function go(next: { page?: number; tgid?: string }) {
    const q = new URLSearchParams(params);
    if (next.page) q.set("page", String(next.page));
    if (next.tgid !== undefined) {
      if (next.tgid) q.set("tgid", next.tgid);
      else q.delete("tgid");
      q.set("page", "1");
    }
    setParams(q);
  }

  function onSearch(e: FormEvent) {
    e.preventDefault();
    go({ tgid: search.trim() });
  }

  const longLists =
    data?.users.filter((user) => user.subs.length > SUB_PREVIEW).length || 0;

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="max-w-xl space-y-1">
          <h1 className="text-2xl font-bold">Пользователи</h1>
          <Hint>
            Сначала те, у кого живой тариф и много подкастов. Оранжевый чип —
            notify включён, бледно-жёлтый — подкаст просто в списке.
          </Hint>
        </div>
        <form className="flex gap-2" onSubmit={onSearch}>
          <div className="relative">
            <Search
              size={14}
              className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-zinc-500"
            />
            <Input
              className="w-56 pl-8 pr-8"
              placeholder="Telegram ID"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              inputMode="numeric"
            />
            {search ? (
              <button
                type="button"
                className="absolute right-2 top-1/2 -translate-y-1/2 text-zinc-500 hover:text-zinc-200"
                onClick={() => {
                  setSearch("");
                  go({ tgid: "" });
                }}
                aria-label="Сбросить поиск"
              >
                <X size={14} />
              </button>
            ) : null}
          </div>
          <Button type="submit">Найти</Button>
        </form>
      </div>
      {isLoading || !data ? (
        <div className="space-y-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-24 w-full" />
          ))}
        </div>
      ) : (
        <>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <Hint>
              {data.total} чел. · страница {data.page} / {data.pages} · по{" "}
              {data.per_page} на странице. Длинные списки подкастов свёрнуты.
            </Hint>
            {longLists > 0 ? (
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => setExpandAll((v) => !v)}
              >
                {expandAll
                  ? "Свернуть все списки"
                  : `Развернуть длинные списки (${longLists})`}
              </Button>
            ) : null}
          </div>
          <div className="space-y-4">
            {data.users.map((user) => (
              <UserCard
                key={user.id}
                user={user}
                defaultOpen={!!tgid}
                forceSubsOpen={expandAll}
                onFilter={(id) => {
                  setSearch(id);
                  go({ tgid: id });
                }}
              />
            ))}
          </div>
          {data.pages > 1 && !tgid ? (
            <div className="flex items-center gap-2">
              <Button
                variant="outline"
                disabled={page <= 1}
                onClick={() => go({ page: page - 1 })}
              >
                Назад
              </Button>
              <span className="text-sm text-zinc-400">
                {page} / {data.pages}
              </span>
              <Button
                variant="outline"
                disabled={page >= data.pages}
                onClick={() => go({ page: page + 1 })}
              >
                Дальше
              </Button>
            </div>
          ) : tgid ? (
            <Button
              variant="outline"
              onClick={() => {
                setSearch("");
                go({ tgid: "" });
              }}
            >
              Все пользователи
            </Button>
          ) : null}
        </>
      )}
    </div>
  );
}
