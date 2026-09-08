import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Card, Hint, Skeleton } from "@/components/ui/primitives";

const cards: {
  key:
    | "total"
    | "with_subs"
    | "with_subs_notify"
    | "with_bot_sub"
    | "receive_episodes"
    | "digest_reminder"
    | "blocked";
  label: string;
  hint: string;
}[] = [
  {
    key: "total",
    label: "Живые пользователи",
    hint: "Аккаунт не помечен как удалённый: человек не заблокировал бота.",
  },
  {
    key: "with_subs",
    label: "С подписками",
    hint: "Хотя бы один подкаст в списке, даже если уведомления выключены.",
  },
  {
    key: "with_subs_notify",
    label: "Notify включён",
    hint: "Уведомления (notify) стоят хотя бы на одном подкасте. Это ещё не значит, что уходит аудио.",
  },
  {
    key: "with_bot_sub",
    label: "Подписка на бота",
    hint: "Живой тариф: выбран план, осталось время, лимит уведомлений не ноль (−1 = без лимита).",
  },
  {
    key: "receive_episodes",
    label: "Получают выпуски",
    hint: "Живой тариф и notify на подкасте — им бот реально шлёт новые эпизоды.",
  },
  {
    key: "digest_reminder",
    label: "Дайджест без тарифа",
    hint: "Notify на подкасте есть, живого тарифа нет. В конце круга уходит текстовое «есть новые выпуски», без аудио.",
  },
  {
    key: "blocked",
    label: "Заблокировали",
    hint: "У бота deleted_at: человек остановил или удалил чат. В живых их уже нет.",
  },
];

export default function Dashboard() {
  const { data, isLoading } = useQuery({
    queryKey: ["stats"],
    queryFn: api.stats,
  });

  return (
    <div className="min-w-0 space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Статистика</h1>
        <Hint>
          Счётчики по живой базе. Карточки ниже — разные срезы одних и тех же
          людей, их нельзя складывать.
        </Hint>
      </div>
      <div className="grid min-w-0 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {cards.map((card) => (
          <Card key={card.key} className="flex flex-col gap-2">
            <div className="text-xs font-medium uppercase tracking-wide text-zinc-500">
              {card.label}
            </div>
            {isLoading || !data ? (
              <Skeleton className="h-9 w-24" />
            ) : (
              <div className="text-3xl font-bold text-brand">
                {data[card.key] as number}
              </div>
            )}
            <Hint>{card.hint}</Hint>
          </Card>
        ))}
      </div>
      <div className="grid min-w-0 gap-4 lg:grid-cols-2">
        <Card>
          <h2 className="mb-1 font-semibold">Круг апдейтера</h2>
          <Hint className="mb-4">
            Фоновый обход RSS всех подкастов. «Обход A / B» — текущий канал из
            максимального id. После круга пишутся длительность и сколько кругов
            прошло за сегодня.
          </Hint>
          {isLoading || !data ? (
            <div className="space-y-2">
              <Skeleton className="h-4 w-2/3" />
              <Skeleton className="h-4 w-1/2" />
            </div>
          ) : (
            <div className="space-y-1 text-sm text-zinc-300 [overflow-wrap:anywhere]">
              <div>
                Обход: {data.updater_channel_id} / {data.max_channel_id}
              </div>
              {data.circle_status ? (
                data.circle_status.split("\n").map((line) => (
                  <div key={line}>{line}</div>
                ))
              ) : (
                <div className="text-zinc-500">
                  Круг ещё не завершался после последнего запуска.
                </div>
              )}
            </div>
          )}
        </Card>
        <Card>
          <h2 className="mb-1 font-semibold">Языки</h2>
          <Hint className="mb-4">
            Язык интерфейса из профиля. Только живые пользователи. «—» — язык
            ещё не выбран.
          </Hint>
          {isLoading || !data ? (
            <div className="space-y-2">
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-4 w-5/6" />
              <Skeleton className="h-4 w-2/3" />
            </div>
          ) : (
            <div className="space-y-2">
              {data.by_lang.map((row) => (
                <div key={row.lang} className="flex min-w-0 items-center gap-3 text-sm">
                  <div className="w-10 shrink-0 text-zinc-400">{row.lang}</div>
                  <div className="h-2 min-w-0 flex-1 overflow-hidden rounded-full bg-white/10">
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
                  <div className="w-14 shrink-0 text-right text-zinc-300">{row.count}</div>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}
