import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Card, Skeleton } from "@/components/ui/primitives";

const cards: { key: "total" | "with_subs" | "with_subs_notify" | "with_bot_sub" | "receive_episodes" | "digest_reminder" | "blocked"; label: string }[] = [
  { key: "total", label: "Живые пользователи" },
  { key: "with_subs", label: "С подписками" },
  { key: "with_subs_notify", label: "Подписки + notify" },
  { key: "with_bot_sub", label: "Подписка на бота" },
  { key: "receive_episodes", label: "Получают выпуски" },
  { key: "digest_reminder", label: "Дайджест без тарифа" },
  { key: "blocked", label: "Заблокировали" },
];

export default function Dashboard() {
  const { data, isLoading } = useQuery({
    queryKey: ["stats"],
    queryFn: api.stats,
  });

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Статистика</h1>
        <p className="text-sm text-zinc-500">
          Те же цифры, что в PHP, плюс здоровье круга апдейтера.
        </p>
      </div>
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {cards.map((card) => (
          <Card key={card.key} className="space-y-2">
            <div className="text-xs uppercase tracking-wide text-zinc-500">
              {card.label}
            </div>
            {isLoading || !data ? (
              <Skeleton className="h-9 w-24" />
            ) : (
              <div className="text-3xl font-bold text-brand">
                {data[card.key] as number}
              </div>
            )}
          </Card>
        ))}
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <h2 className="mb-4 font-semibold">Круг апдейтера</h2>
          {isLoading || !data ? (
            <div className="space-y-2">
              <Skeleton className="h-4 w-2/3" />
              <Skeleton className="h-4 w-1/2" />
            </div>
          ) : (
            <div className="space-y-1 text-sm text-zinc-300">
              <div>
                Обход: {data.updater_channel_id} / {data.max_channel_id}
              </div>
              {data.circle_status
                ? data.circle_status.split("\n").map((line) => (
                    <div key={line}>{line}</div>
                  ))
                : <div className="text-zinc-500">Круг ещё не завершался после деплоя.</div>}
            </div>
          )}
        </Card>
        <Card>
          <h2 className="mb-4 font-semibold">Языки</h2>
          {isLoading || !data ? (
            <div className="space-y-2">
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-4 w-5/6" />
              <Skeleton className="h-4 w-2/3" />
            </div>
          ) : (
            <div className="space-y-2">
              {data.by_lang.map((row) => (
                <div key={row.lang} className="flex items-center gap-3 text-sm">
                  <div className="w-10 text-zinc-400">{row.lang}</div>
                  <div className="h-2 flex-1 overflow-hidden rounded-full bg-white/10">
                    <div
                      className="h-full bg-brand"
                      style={{
                        width: `${Math.max(
                          4,
                          (row.count / Math.max(data.total, 1)) * 100,
                        )}%`,
                      }}
                    />
                  </div>
                  <div className="w-14 text-right text-zinc-300">{row.count}</div>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}
