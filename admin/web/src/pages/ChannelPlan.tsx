import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, ChannelPlan } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card, Field, Hint, Skeleton, Textarea } from "@/components/ui/primitives";

const refOf = (c: ChannelPlan["channels"][number]) => c.ref || String(c.id);

/** What saving does to the people who hold it now: asked before, null when nothing happens to them. */
function consequence(plan: ChannelPlan, enabled: boolean, lines: string[]): string | null {
  const holders = plan.grants.running;
  if (!holders || !plan.enabled) return null;
  if (!enabled || !lines.length) {
    return `У ${holders} чел. бесплатная Бронза закончится в течение часа, им придёт сообщение с тарифами. Выключить?`;
  }
  const had = new Set(plan.channels.map(refOf));
  if (lines.some((line) => !had.has(line))) {
    return (
      `Новый канал нужен и тем ${holders} чел., у кого Бронза уже есть: кто на него не подписан, получит ` +
      `сообщение и ${plan.grace_hours} ч, чтобы подписаться, иначе Бронза закончится. Сохранить?`
    );
  }
  return null;
}

function Form({ plan }: { plan: ChannelPlan }) {
  const queryClient = useQueryClient();
  const [channels, setChannels] = useState(plan.channels.map(refOf).join("\n"));
  const [enabled, setEnabled] = useState(plan.enabled);
  const save = useMutation({
    mutationFn: api.saveChannelPlan,
    onSuccess: (data) => queryClient.setQueryData(["channelPlan"], data),
  });
  // "@a, @b; @c" on one line or one per line: a ref never holds a comma, a semicolon or a space
  const lines = channels.split(/[\s,;]+/).filter(Boolean);
  const submit = () => {
    const ask = consequence(plan, enabled, lines);
    if (ask && !window.confirm(ask)) return;
    save.mutate({ enabled: enabled && lines.length > 0, channels: lines });
  };
  return (
    <div className="space-y-4">
      <label className="flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          className="h-4 w-4"
          checked={enabled && lines.length > 0}
          disabled={!lines.length}
          onChange={(e) => setEnabled(e.target.checked)}
        />
        Акция включена{lines.length ? "" : " (нужен хотя бы один канал)"}
      </label>
      <Field
        label="Каналы через запятую, пробел или с новой строки: нужна подписка на все"
        hint="@имя, ссылка t.me/имя или id -100…. Бот должен быть админом каждого канала: иначе Telegram не скажет, кто подписан. Приватному каналу бот сам сделает ссылку-приглашение."
      >
        <Textarea rows={4} value={channels} onChange={(e) => setChannels(e.target.value)} />
      </Field>
      <div className="flex items-center gap-3">
        <Button size="sm" disabled={save.isPending} onClick={submit}>
          {save.isPending ? "Проверяю каналы…" : "Сохранить"}
        </Button>
        {save.isError ? <span className="text-sm text-red-400 wrap-anywhere">{save.error.message}</span> : null}
        {save.isSuccess ? <span className="text-sm text-emerald-400">Сохранено</span> : null}
      </div>
      {plan.channels.length ? (
        <ul className="space-y-1 text-sm">
          {plan.channels.map((c) => (
            <li key={c.id} className="wrap-anywhere">
              <a className="text-sky-400 hover:underline" href={c.url} target="_blank" rel="noreferrer">
                {c.title}
              </a>{" "}
              <span className="text-zinc-500">{c.id}</span>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

export default function ChannelPlanCard() {
  const { data, isLoading } = useQuery({ queryKey: ["channelPlan"], queryFn: api.channelPlan });
  return (
    <Card className="space-y-4">
      <div className="space-y-1">
        <div className="text-lg font-semibold">Бронза за подписку на каналы</div>
        <Hint>
          Бесплатная Бронза без ИИ, пока человек подписан на все каналы из списка. Даётся, только когда у него
          нет другого тарифа; любая оплата или смена тарифа её заменяет. Бот проверяет подписки каждый час:
          не хватает канала (отписался или вы добавили новый), и человек получает предупреждение и
          {data ? ` ${data.grace_hours} ч` : " сутки"}, чтобы подписаться, потом Бронза выключается с
          сообщением и всеми тарифами. Выключили акцию или убрали все каналы: кнопка в /subscription пропадает,
          а у держателей Бронза заканчивается в течение часа с сообщением. Убрать канал можно без последствий.
        </Hint>
      </div>
      {isLoading || !data ? (
        <Skeleton className="h-24 w-full" />
      ) : (
        <>
          <div className="text-sm text-zinc-400">
            {data.enabled ? "Включена" : "Выключена"} · сейчас действует: {data.grants.running} · за 30 дней
            включили: {data.grants.started} · выключились: {data.grants.ended}
          </div>
          <Form key={JSON.stringify([data.channels, data.enabled])} plan={data} />
        </>
      )}
    </Card>
  );
}
