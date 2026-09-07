import { FormEvent, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Badge, Card, Input, Skeleton } from "@/components/ui/primitives";

export default function Users() {
  const [params, setParams] = useSearchParams();
  const page = Number(params.get("page") || "1");
  const tgid = params.get("tgid") || "";
  const [search, setSearch] = useState(tgid);
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

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold">Пользователи</h1>
          <p className="text-sm text-zinc-500">
            Подписки грузятся одним запросом на страницу, без N+1.
          </p>
        </div>
        <form className="flex gap-2" onSubmit={onSearch}>
          <Input
            placeholder="telegram id"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
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
          <div className="text-sm text-zinc-500">
            {data.total} чел. · страница {data.page} / {data.pages}
          </div>
          <div className="space-y-4">
            {data.users.map((user) => (
              <Card key={user.id} className="space-y-3">
                <div className="flex flex-wrap items-center gap-2 text-sm">
                  <button
                    className="font-mono text-brand hover:underline"
                    onClick={() => go({ tgid: String(user.telegramId) })}
                  >
                    {user.id} · {user.telegramId}
                  </button>
                  <Badge>{user.lang || "—"}</Badge>
                  {user.deleted ? <Badge tone="mute">blocked</Badge> : null}
                  {user.receives_episodes ? (
                    <Badge tone="warn">получает выпуски</Badge>
                  ) : null}
                  <span className="text-zinc-500">
                    подписок: {user.channels_count}
                  </span>
                </div>
                <div className="text-xs text-zinc-400">
                  Tariff {user.tariff_id ?? "—"} · balance {user.balance ?? "—"} ·
                  time {user.time_left ?? "—"}
                  {user.time_left_days != null
                    ? ` (${user.time_left_days.toFixed(1)} дн.)`
                    : ""}{" "}
                  · notify {user.notify_count ?? "—"}
                </div>
                {user.receives_episodes ? (
                  <div className="rounded-lg bg-red-600/80 px-3 py-2 text-sm font-medium">
                    Получает уведомления
                  </div>
                ) : null}
                {user.subs.length ? (
                  <div className="flex flex-wrap gap-1">
                    {user.subs.map((sub) => (
                      <span
                        key={sub.name}
                        className={`rounded px-2 py-1 text-xs text-black ${
                          sub.notify ? "bg-brand" : "bg-yellow-200/80"
                        }`}
                      >
                        {sub.name}
                      </span>
                    ))}
                  </div>
                ) : null}
              </Card>
            ))}
          </div>
          {data.pages > 1 && !tgid ? (
            <div className="flex gap-2">
              <Button
                variant="outline"
                disabled={page <= 1}
                onClick={() => go({ page: page - 1 })}
              >
                Назад
              </Button>
              <Button
                variant="outline"
                disabled={page >= data.pages}
                onClick={() => go({ page: page + 1 })}
              >
                Дальше
              </Button>
            </div>
          ) : tgid ? (
            <Button variant="outline" onClick={() => go({ tgid: "" })}>
              Все пользователи
            </Button>
          ) : null}
        </>
      )}
    </div>
  );
}
