import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, PlanFeatures, PlanProfiles } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card, Hint, Input, Skeleton } from "@/components/ui/primitives";

const PROFILE_NAMES: Record<string, string> = {
  none: "Без тарифа",
  trial: "Пробный (никто не платил)",
  "level:1": "Бронза (оплачена)",
  "level:2": "Серебро (оплачено)",
  "level:3": "Relay (оплачен)",
  "grant:channels": "Бронза за каналы",
};

const FEATURE_NAMES: Record<string, string> = {
  ai: "ИИ вообще",
  ai_hours: "Часов аудио за 30 дней",
  ai_paid_hours: "Из них точной моделью",
  ai_questions_day: "Вопросов за 24 ч",
  ai_questions_month: "Вопросов за 30 дней",
  ai_budget: "Бюджет от цены",
  clicks: "Выпусков по клику (пусто: без лимита)",
  clicks_hours: "Окно кликов, часов",
};

function Column({ name, data }: { name: string; data: PlanProfiles }) {
  const queryClient = useQueryClient();
  const [draft, setDraft] = useState<PlanFeatures>(data.profiles[name]);
  const save = useMutation({
    mutationFn: api.savePlanProfile,
    onSuccess: (next) => queryClient.setQueryData(["planProfiles"], next),
  });
  const edited = Object.keys(data.edits[name] || {});
  return (
    <td className="space-y-2 px-2 py-2 align-top">
      {Object.keys(data.features).map((key) => {
        const value = draft[key];
        const changed = edited.includes(key);
        return (
          <div key={key} className="h-10" title={`По умолчанию: ${String(data.defaults[name][key])}`}>
            {typeof data.defaults[name][key] === "boolean" ? (
              <input
                type="checkbox"
                className="mt-3 h-4 w-4"
                checked={Boolean(value)}
                onChange={(e) => setDraft({ ...draft, [key]: e.target.checked })}
              />
            ) : (
              <Input
                type="number"
                min={0}
                className={changed ? "border-amber-500" : undefined}
                value={value === null ? "" : String(value)}
                placeholder={key === "clicks" ? "без лимита" : undefined}
                onChange={(e) =>
                  setDraft({
                    ...draft,
                    [key]: e.target.value === "" && key === "clicks" ? null : Number(e.target.value),
                  })
                }
              />
            )}
          </div>
        );
      })}
      <div className="flex flex-wrap gap-2 pt-1">
        <Button size="sm" disabled={save.isPending} onClick={() => save.mutate({ name, features: draft })}>
          {save.isPending ? "…" : "Сохранить"}
        </Button>
        {edited.length ? (
          <Button size="sm" variant="ghost" disabled={save.isPending} onClick={() => save.mutate({ name, features: {} })}>
            Сбросить
          </Button>
        ) : null}
      </div>
      {save.isError ? <div className="text-xs text-red-400 wrap-anywhere">{save.error.message}</div> : null}
    </td>
  );
}

export default function PlanProfilesCard() {
  const { data, isLoading } = useQuery({ queryKey: ["planProfiles"], queryFn: api.planProfiles });
  return (
    <Card className="max-w-full space-y-4 overflow-x-auto">
      <div className="space-y-1">
        <div className="text-lg font-semibold">Что даёт каждый вид тарифа</div>
        <Hint>
          Права по видам тарифа: без тарифа, пробный (тариф идёт, но за него не платили), оплаченный по уровню,
          Бронза за каналы. По умолчанию значения из config.py; правка хранится отдельно и доходит до бота за
          {data ? ` ${data.cache_seconds} с` : " минуту"}. Изменённые поля подсвечены, подсказка над полем
          показывает значение по умолчанию. Доставка выпусков (лимит notify, каналы) остаётся в таблице выше.
        </Hint>
      </div>
      {isLoading || !data ? (
        <Skeleton className="h-64 w-full" />
      ) : (
        <table className="w-full min-w-[960px] text-sm">
          <thead className="text-left text-zinc-500">
            <tr>
              <th className="px-3 py-3"></th>
              {Object.keys(data.profiles).map((name) => (
                <th key={name} className="px-2 py-3">
                  {PROFILE_NAMES[name] || name}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            <tr className="border-t border-line">
              <td className="space-y-2 px-3 py-2 align-top">
                {Object.entries(data.features).map(([key, meaning]) => (
                  <div key={key} className="flex h-10 items-center" title={meaning}>
                    {FEATURE_NAMES[key] || key}
                  </div>
                ))}
              </td>
              {Object.keys(data.profiles).map((name) => (
                <Column key={`${name}-${JSON.stringify(data.profiles[name])}`} name={name} data={data} />
              ))}
            </tr>
          </tbody>
        </table>
      )}
    </Card>
  );
}
