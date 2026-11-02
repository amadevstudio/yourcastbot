import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api, type AiPlan, type AiRate, type EconomicsRow } from "@/lib/api";
import { Badge, Card, Hint, Skeleton } from "@/components/ui/primitives";
import { Button } from "@/components/ui/button";

const periods = [7, 30, 90];

const segmentLabels: Record<string, string> = {
  paid: "Платят",
  trial: "Пробный период",
  free: "Бесплатные",
};

const segmentTones: Record<string, "ok" | "default" | "mute"> = {
  paid: "ok",
  trial: "default",
  free: "mute",
};

const planLabels: Record<string, string> = {
  "1": "Bronze",
  "2": "Silver",
  "3": "Relay",
  trial: "Пробный",
};

type SortKey = "margin_asc" | "margin_desc" | "load";

function usd(value: number) {
  const sign = value < 0 ? "−" : "";
  const abs = Math.abs(value);
  return `${sign}$${abs < 1 && abs > 0 ? abs.toFixed(3) : abs.toFixed(2)}`;
}

function rate(r: AiRate, unit: string) {
  return r.usd === null ? "нет данных" : `${usd(r.usd)}${unit} (${r.n})`;
}

function worst(value: number | null, price: number) {
  if (value === null) return <span className="text-zinc-500">–</span>;
  const share = price > 0 ? ` · ${Math.round((value / price) * 100)}%` : "";
  return (
    <span className={price > 0 && value > price ? "font-medium text-red-400" : undefined}>
      {usd(value)}
      <span className="text-zinc-500">{share}</span>
    </span>
  );
}

function AiPlans({ plans, days }: { plans: AiPlan[]; days: number }) {
  return (
    <div className="min-w-0 overflow-x-auto">
      <table className="w-full min-w-[760px] text-sm">
        <thead className="text-left text-xs uppercase tracking-wide text-zinc-500">
          <tr>
            <th className="py-2 pr-3">Тариф</th>
            <th className="py-2 pr-3 text-right">Цена</th>
            <th className="py-2 pr-3 text-right">Часов / вопросов в день</th>
            <th className="py-2 pr-3 text-right">Худший месяц: Whisper</th>
            <th className="py-2 pr-3 text-right">Худший месяц: платная модель</th>
            <th className="py-2 pr-3 text-right">Чатов (с ИИ)</th>
            <th className="py-2 pr-3 text-right">Часов за {days} дн. (макс. на чат)</th>
            <th className="py-2 text-right">ИИ за {days} дн.</th>
          </tr>
        </thead>
        <tbody>
          {plans.map((p) => (
            <tr key={p.key} className="border-t border-line">
              <td className="py-2 pr-3">{planLabels[p.key] ?? `Уровень ${p.level}`}</td>
              <td className="py-2 pr-3 text-right">{p.price_usd > 0 ? usd(p.price_usd) : "–"}</td>
              <td className="py-2 pr-3 text-right">
                {p.hours} / {p.questions_per_day}
              </td>
              <td className="py-2 pr-3 text-right">{worst(p.worst_whisper_usd, p.price_usd)}</td>
              <td className="py-2 pr-3 text-right">{worst(p.worst_paid_usd, p.price_usd)}</td>
              <td className="py-2 pr-3 text-right">
                {p.chats} ({p.ai_chats})
              </td>
              <td className="py-2 pr-3 text-right">
                {p.hours_used.toFixed(1)} ({p.max_hours.toFixed(1)})
              </td>
              <td className="py-2 text-right">{usd(p.ai_usd)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function load(row: EconomicsRow, mbPerUnit: number) {
  return row.rec + row.circle + row.mb / mbPerUnit;
}

export default function Economics() {
  const [days, setDays] = useState(30);
  const [sort, setSort] = useState<SortKey>("margin_asc");
  const { data, isLoading } = useQuery({
    queryKey: ["economics", days],
    queryFn: () => api.economics(days),
  });

  const rows = data
    ? [...data.users].sort((a, b) => {
        if (sort === "margin_desc") return b.margin_usd - a.margin_usd;
        if (sort === "load")
          return load(b, data.load_mb_per_unit) - load(a, data.load_mb_per_unit);
        return a.margin_usd - b.margin_usd;
      })
    : [];

  const cards = data
    ? [
        { label: "Выручка", value: usd(data.totals.revenue_usd), hint: "Оплаты за период, без ваших тестовых." },
        { label: "ИИ", value: usd(data.totals.ai_usd), hint: "Сколько взяли API за пересказы." },
        {
          label: "Сервер",
          value: usd(data.totals.fixed_usd),
          hint: `$${data.server_usd_month}/мес, доля периода. Делится между пользователями по нагрузке.`,
        },
        {
          label: "Итог",
          value: usd(data.totals.margin_usd),
          hint: "Выручка минус ИИ минус сервер.",
        },
      ]
    : [];

  return (
    <div className="min-w-0 space-y-6">
      <div className="flex min-w-0 flex-wrap items-end justify-between gap-3">
        <div className="max-w-xl min-w-0 space-y-1">
          <h1 className="text-2xl font-bold">Экономика</h1>
          <Hint>
            Кто приносит деньги и кто их стоит. Нагрузка: одна доставка эпизода
            – одна единица, {data?.load_mb_per_unit ?? 50} МБ, скачанных
            сервером, – ещё одна. Каналы считаются за их владельцем.
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

      <div className="grid min-w-0 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {isLoading || !data
          ? Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-28 w-full" />)
          : cards.map((card) => (
              <Card key={card.label} className="flex flex-col gap-2">
                <div className="text-xs font-medium uppercase tracking-wide text-zinc-500">
                  {card.label}
                </div>
                <div className="text-3xl font-bold text-brand">{card.value}</div>
                <Hint>{card.hint}</Hint>
              </Card>
            ))}
      </div>

      <Card className="min-w-0">
        <h2 className="mb-1 font-semibold">Сегменты</h2>
        <Hint className="mb-4">
          По тарифу сейчас. "Пробный период" – тариф идёт, но за него никто не
          платил (приветственные или реферальные дни).
        </Hint>
        {isLoading || !data ? (
          <Skeleton className="h-24 w-full" />
        ) : (
          <div className="min-w-0 overflow-x-auto">
            <table className="w-full min-w-[640px] text-sm">
              <thead className="text-left text-xs uppercase tracking-wide text-zinc-500">
                <tr>
                  <th className="py-2 pr-3">Сегмент</th>
                  <th className="py-2 pr-3 text-right">Людей</th>
                  <th className="py-2 pr-3 text-right">Клики</th>
                  <th className="py-2 pr-3 text-right">Авто</th>
                  <th className="py-2 pr-3 text-right">МБ</th>
                  <th className="py-2 pr-3 text-right">ИИ</th>
                  <th className="py-2 pr-3 text-right">Выручка</th>
                  <th className="py-2 pr-3 text-right">Сервер</th>
                  <th className="py-2 text-right">Итог</th>
                </tr>
              </thead>
              <tbody>
                {data.segments.map((s) => (
                  <tr key={s.segment} className="border-t border-line">
                    <td className="py-2 pr-3">
                      <Badge tone={segmentTones[s.segment]}>{segmentLabels[s.segment]}</Badge>
                    </td>
                    <td className="py-2 pr-3 text-right">{s.users}</td>
                    <td className="py-2 pr-3 text-right">{s.rec}</td>
                    <td className="py-2 pr-3 text-right">{s.circle}</td>
                    <td className="py-2 pr-3 text-right">{Math.round(s.mb)}</td>
                    <td className="py-2 pr-3 text-right">{usd(s.ai_usd)}</td>
                    <td className="py-2 pr-3 text-right">{usd(s.revenue_usd)}</td>
                    <td className="py-2 pr-3 text-right">{usd(s.fixed_usd)}</td>
                    <td
                      className={`py-2 text-right font-medium ${
                        s.margin_usd < 0 ? "text-red-400" : "text-tg"
                      }`}
                    >
                      {usd(s.margin_usd)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <Card className="min-w-0">
        <h2 className="mb-1 font-semibold">ИИ по тарифам</h2>
        <Hint className="mb-4">
          Худший месяц – если чат потратит все часы тарифа на новые выпуски (по
          пересказу на час) и задаст все вопросы каждого дня. Процент – доля от
          цены, красным – дороже цены. Stars продаются по курсу вывода, так что
          цена приходит целиком. Выпуск, который уже кто-то расшифровал, часов
          не тратит и ничего не стоит.
          {data && (
            <>
              {" "}
              Ставки по факту (сколько сделано): Whisper{" "}
              {rate(data.ai.rates.whisper, "/ч")}, платная модель{" "}
              {rate(data.ai.rates.speakers, "/ч")}, пересказ{" "}
              {rate(data.ai.rates.summary, "")}, вопрос {rate(data.ai.rates.question, "")}.
              {data.ai.paid_model
                ? ` Платная модель: ${data.ai.paid_model}, только у тех, кто платил.`
                : " Платная модель не включена."}
            </>
          )}
        </Hint>
        {isLoading || !data ? (
          <Skeleton className="h-32 w-full" />
        ) : (
          <AiPlans plans={data.ai.plans} days={data.days} />
        )}
      </Card>

      <Card className="min-w-0">
        <div className="mb-1 flex min-w-0 flex-wrap items-center justify-between gap-2">
          <h2 className="font-semibold">Пользователи</h2>
          <div className="flex flex-wrap gap-2">
            <Button
              size="sm"
              variant={sort === "margin_asc" ? "default" : "outline"}
              onClick={() => setSort("margin_asc")}
            >
              Самые убыточные
            </Button>
            <Button
              size="sm"
              variant={sort === "margin_desc" ? "default" : "outline"}
              onClick={() => setSort("margin_desc")}
            >
              Самые прибыльные
            </Button>
            <Button
              size="sm"
              variant={sort === "load" ? "default" : "outline"}
              onClick={() => setSort("load")}
            >
              Нагрузка
            </Button>
          </div>
        </div>
        <Hint className="mb-4">
          Те, кто пользовался ботом или платил за период (до 500). Telegram ID
          открывает карточку пользователя.
        </Hint>
        {isLoading || !data ? (
          <Skeleton className="h-48 w-full" />
        ) : rows.length === 0 ? (
          <Hint>За этот период событий ещё нет: учёт идёт с момента выкатки.</Hint>
        ) : (
          <div className="min-w-0 overflow-x-auto">
            <table className="w-full min-w-[720px] text-sm">
              <thead className="text-left text-xs uppercase tracking-wide text-zinc-500">
                <tr>
                  <th className="py-2 pr-3">Telegram ID</th>
                  <th className="py-2 pr-3">Сегмент</th>
                  <th className="py-2 pr-3 text-right">Клики</th>
                  <th className="py-2 pr-3 text-right">Авто</th>
                  <th className="py-2 pr-3 text-right">МБ</th>
                  <th className="py-2 pr-3 text-right">ИИ</th>
                  <th className="py-2 pr-3 text-right">Выручка</th>
                  <th className="py-2 pr-3 text-right">Сервер</th>
                  <th className="py-2 text-right">Итог</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.tg} className="border-t border-line">
                    <td className="py-2 pr-3">
                      <Link className="text-brand hover:underline" to={`/users?tgid=${row.tg}`}>
                        {row.tg}
                      </Link>
                    </td>
                    <td className="py-2 pr-3">
                      <Badge tone={segmentTones[row.segment]}>{segmentLabels[row.segment]}</Badge>
                    </td>
                    <td className="py-2 pr-3 text-right">{row.rec}</td>
                    <td className="py-2 pr-3 text-right">{row.circle}</td>
                    <td className="py-2 pr-3 text-right">{Math.round(row.mb)}</td>
                    <td className="py-2 pr-3 text-right">{usd(row.ai_usd)}</td>
                    <td className="py-2 pr-3 text-right">{usd(row.revenue_usd)}</td>
                    <td className="py-2 pr-3 text-right">{usd(row.fixed_usd)}</td>
                    <td
                      className={`py-2 text-right font-medium ${
                        row.margin_usd < 0 ? "text-red-400" : "text-tg"
                      }`}
                    >
                      {usd(row.margin_usd)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
