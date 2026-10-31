import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, type ProductFunnel } from "@/lib/api";
import { Card, Hint, Skeleton } from "@/components/ui/primitives";
import { Button } from "@/components/ui/button";

const periods = [7, 30, 90];

const funnel: { key: keyof ProductFunnel; label: string; hint: string }[] = [
  { key: "new", label: "Пришли", hint: "Новые пользователи за период." },
  {
    key: "own_sub",
    label: "Подписались сами",
    hint: "Хотя бы один подкаст, кроме приветственного (на него бот подписывает всех).",
  },
  { key: "got_episode", label: "Получили выпуск", hint: "По клику или автоматически." },
  { key: "asked_summary", label: "Просили пересказ", hint: "Кнопкой или автопересказом." },
  { key: "paid", label: "Заплатили", hint: "Хотя бы одна оплата, без ваших тестовых." },
  { key: "blocked", label: "Заблокировали бота", hint: "Остановили или удалили чат." },
];

function pct(part: number, whole: number) {
  return whole ? Math.round((part / whole) * 100) : 0;
}

function pct1(part: number, whole: number) {
  return whole ? ((part / whole) * 100).toFixed(1) : "0.0";
}

function usd(value: number) {
  return `$${value < 1 && value > 0 ? value.toFixed(3) : value.toFixed(2)}`;
}

function Metric({ label, value, hint }: { label: string; value: string | number; hint?: string }) {
  return (
    <div className="min-w-0 space-y-1">
      <div className="text-xs font-medium uppercase tracking-wide text-zinc-500">{label}</div>
      <div className="text-2xl font-bold text-brand">{value}</div>
      {hint ? <Hint>{hint}</Hint> : null}
    </div>
  );
}

export default function Product() {
  const [days, setDays] = useState(30);
  const { data, isLoading } = useQuery({
    queryKey: ["product", days],
    queryFn: () => api.product(days),
  });

  return (
    <div className="min-w-0 space-y-6">
      <div className="flex min-w-0 flex-wrap items-end justify-between gap-3">
        <div className="max-w-xl min-w-0 space-y-1">
          <h1 className="text-2xl font-bold">Продукт</h1>
          <Hint>
            Что делают новички, кто на каком тарифе, как пользуются пересказами
            и вопросами. Деньги по людям – в "Экономике", нажатия и переходы из
            дайджеста – в Amplitude.
            {data?.ledger_since
              ? ` Доставки и вопросы считаются с ${data.ledger_since.slice(0, 10)}.`
              : ""}
          </Hint>
        </div>
        <div className="flex gap-2">
          {periods.map((p) => (
            <Button
              key={p}
              variant={p === days ? "default" : "outline"}
              size="sm"
              onClick={() => setDays(p)}
            >
              {p} дн.
            </Button>
          ))}
        </div>
      </div>

      {isLoading || !data ? (
        <div className="space-y-4">
          <Skeleton className="h-64 w-full" />
          <Skeleton className="h-40 w-full" />
        </div>
      ) : (
        <>
          <Card className="min-w-0">
            <h2 className="mb-1 font-semibold">Новички за {data.days} дн.</h2>
            <Hint className="mb-4">Каждая строка – доля от пришедших за период.</Hint>
            <div className="space-y-3">
              {funnel.map((step) => {
                const value = data.newcomers[step.key];
                const share = pct(value, data.newcomers.new);
                return (
                  <div key={step.key} className="min-w-0">
                    <div className="flex min-w-0 items-baseline justify-between gap-3 text-sm">
                      <span className="min-w-0 truncate" title={step.hint}>
                        {step.label}
                      </span>
                      <span className="shrink-0 font-medium">
                        {value}
                        {step.key === "new" ? "" : ` · ${share}%`}
                      </span>
                    </div>
                    <div className="mt-1 h-2 w-full overflow-hidden rounded bg-white/5">
                      <div
                        className={`h-full rounded ${step.key === "blocked" ? "bg-red-400/70" : "bg-brand"}`}
                        style={{ width: `${step.key === "new" ? 100 : share}%` }}
                      />
                    </div>
                  </div>
                );
              })}
            </div>
          </Card>

          <Card className="min-w-0">
            <h2 className="mb-1 font-semibold">
              Заплатили в первые {data.paid_first_days.days} дн.
            </h2>
            <Hint className="mb-4">
              Новички периода, у которых эти {data.paid_first_days.days} дн. уже прошли. Доля не
              меняется от того, когда начинается и кончается пробный период.
            </Hint>
            {data.paid_first_days.matured === 0 ? (
              <Hint>Среди пришедших за {data.days} дн. таких ещё нет: выберите 90 дн.</Hint>
            ) : (
              <div className="grid gap-4 sm:grid-cols-2">
                <Metric
                  label="Все новички"
                  value={`${pct(data.paid_first_days.paid, data.paid_first_days.matured)}%`}
                  hint={`${data.paid_first_days.paid} из ${data.paid_first_days.matured}.`}
                />
                <Metric
                  label="Подписались сами"
                  value={`${pct(data.paid_first_days.own_sub_paid, data.paid_first_days.own_sub)}%`}
                  hint={`${data.paid_first_days.own_sub_paid} из ${data.paid_first_days.own_sub}: подкаст, кроме приветственного.`}
                />
              </div>
            )}
          </Card>

          <Card className="min-w-0">
            <h2 className="mb-1 font-semibold">Напоминание "свой подкаст": A/B</h2>
            <Hint className="mb-4">
              Новички без своего подкаста через 1–6 ч после /start, все с начала теста (период страницы
              не влияет). Чётный id – напоминание, нечётный – контроль. Решение 30.11 по пришедшим до
              23.11: у кого через неделю свой подкаст, "назначено" (получили и не дошло) против контроля.
            </Hint>
            {data.nudge.length === 0 ? (
              <Hint>В группах ещё никого нет.</Hint>
            ) : (
              <>
                <div className="grid gap-4 sm:grid-cols-2">
                  {(["assigned", "control"] as const).map((key) => {
                    const g = data.nudge_read[key];
                    return (
                      <Metric
                        key={key}
                        label={key === "assigned" ? "Назначено" : "Контроль"}
                        value={g.matured === 0 ? "–" : `${pct(g.matured_own_sub, g.matured)}%`}
                        hint={`Прошла неделя у ${g.matured} из ${g.new}: свой подкаст у ${g.matured_own_sub}, заблокировали за неделю ${g.matured_blocked}.`}
                      />
                    );
                  })}
                </div>
                <div className="mt-4 grid gap-4 sm:grid-cols-3">
                  {data.nudge.map((g) => (
                    <Metric
                      key={g.group}
                      label={
                        g.group === "sent" ? "Получили" : g.group === "control" ? "Контроль" : "Не дошло"
                      }
                      value={g.new}
                      hint={`Сейчас: свой подкаст у ${g.own_sub}, эпизод получили ${g.got_episode}, заблокировали ${g.blocked}, заплатили ${g.paid}.`}
                    />
                  ))}
                </div>
              </>
            )}
          </Card>

          <Card className="min-w-0">
            <h2 className="mb-1 font-semibold">Дайджест: A/B</h2>
            <Hint className="mb-4">
              Получили дайджест с начала теста (30.10), по разряду десятков id: нечётный – b. Нажатия
              "Слушать" – в Amplitude, решение 20.11. Здесь – сторожевые метрики: выключили, заблокировали,
              и оплаты (сигнал, не статистика).
            </Hint>
            {data.digest_ab.length === 0 ? (
              <Hint>Дайджестов с начала теста ещё не было.</Hint>
            ) : (
              <div className="grid gap-4 sm:grid-cols-2">
                {data.digest_ab.map((v) => (
                  <Metric
                    key={v.variant}
                    label={`Вариант ${v.variant}`}
                    value={v.recipients}
                    hint={`Выключили ${v.muted} (${pct1(v.muted, v.recipients)}%), заблокировали ${v.blocked} (${pct1(v.blocked, v.recipients)}%), заплатили ${v.paid}.`}
                  />
                ))}
              </div>
            )}
          </Card>

          <div className="grid min-w-0 gap-4 lg:grid-cols-2">
            <Card className="min-w-0">
              <h2 className="mb-4 font-semibold">Тарифы сейчас</h2>
              <div className="grid gap-4 sm:grid-cols-3">
                <Metric label="Платные" value={data.plans.paid} hint="Тариф идёт, была оплата." />
                <Metric
                  label="Пробные"
                  value={data.plans.trial}
                  hint="Тариф идёт, за него никто не платил."
                />
                <Metric
                  label="Пробные кончаются"
                  value={data.plans.trial_ending}
                  hint="В ближайшие 3 дня, и баланса на продление нет."
                />
              </div>
            </Card>
            <Card className="min-w-0">
              <h2 className="mb-4 font-semibold">Оплаты за {data.days} дн.</h2>
              <div className="grid gap-4 sm:grid-cols-4">
                <Metric label="Оплат" value={data.payments.payments} />
                <Metric label="Людей" value={data.payments.payers} />
                <Metric label="Впервые" value={data.payments.first_time} />
                <Metric label="Выручка" value={usd(data.payments.revenue_usd)} />
              </div>
            </Card>
            <Card className="min-w-0">
              <h2 className="mb-4 font-semibold">Пересказы и вопросы</h2>
              <div className="grid gap-4 sm:grid-cols-3">
                <Metric
                  label="Пересказы"
                  value={data.ai.summary_taps + data.ai.summary_auto}
                  hint={`Кнопкой ${data.ai.summary_taps}, авто ${data.ai.summary_auto}; готово ${data.ai.summary_done}, не вышло ${data.ai.summary_failed}. Людей: ${data.ai.summary_chats}.`}
                />
                <Metric
                  label="Вопросы"
                  value={data.ai.questions}
                  hint={`Людей: ${data.ai.question_chats}.`}
                />
                <Metric
                  label="Автопересказ"
                  value={data.ai.auto_on}
                  hint={`Включили сейчас. Расход ИИ за период: ${usd(data.ai.ai_usd)}.`}
                />
              </div>
            </Card>
            <Card className="min-w-0">
              <h2 className="mb-4 font-semibold">Выпуски и дайджест</h2>
              <div className="grid gap-4 sm:grid-cols-3">
                <Metric
                  label="Получали выпуски"
                  value={data.activity.listeners}
                  hint={`Людей за период. Авто: ${data.activity.automatic} доставок.`}
                />
                <Metric
                  label="Клики"
                  value={data.activity.clicks}
                  hint={`Кликали: ${data.activity.clickers} чел.`}
                />
                <Metric
                  label="Дайджест"
                  value={data.digest.last_week}
                  hint={`Получили за 7 дней. Выключили: ${data.digest.muted}.`}
                />
              </div>
            </Card>
          </div>

          <Card className="min-w-0">
            <h2 className="mb-1 font-semibold">Новички по неделям</h2>
            <Hint className="mb-4">Неделя – с понедельника, по дате прихода. Что с ними стало к сегодняшнему дню.</Hint>
            {data.weeks.length === 0 ? (
              <Hint>Новичков за период нет.</Hint>
            ) : (
              <div className="min-w-0 overflow-x-auto">
                <table className="w-full min-w-[560px] text-sm">
                  <thead className="text-left text-xs uppercase tracking-wide text-zinc-500">
                    <tr>
                      <th className="py-2 pr-3">Неделя</th>
                      {funnel.map((step) => (
                        <th key={step.key} className="py-2 pr-3 text-right">
                          {step.label}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {data.weeks.map((week) => (
                      <tr key={week.week} className="border-t border-line">
                        <td className="py-2 pr-3 whitespace-nowrap">{week.week}</td>
                        {funnel.map((step) => (
                          <td key={step.key} className="py-2 pr-3 text-right">
                            {week[step.key]}
                            {step.key === "new" || !week.new ? "" : (
                              <span className="text-zinc-500"> {pct(week[step.key], week.new)}%</span>
                            )}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
        </>
      )}
    </div>
  );
}
