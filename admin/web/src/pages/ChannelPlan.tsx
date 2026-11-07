import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, ChannelPlan } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card, Field, Hint, Input, Skeleton, Textarea } from "@/components/ui/primitives";

function Form({ plan }: { plan: ChannelPlan }) {
  const queryClient = useQueryClient();
  const [channels, setChannels] = useState(plan.channels.map((c) => c.ref || String(c.id)).join("\n"));
  const [need, setNeed] = useState(plan.need);
  const save = useMutation({
    mutationFn: api.saveChannelPlan,
    onSuccess: (data) => queryClient.setQueryData(["channelPlan"], data),
  });
  const lines = channels.split("\n").map((l) => l.trim()).filter(Boolean);
  return (
    <div className="space-y-4">
      <Field
        label="Каналы, по одному в строке"
        hint="@имя, ссылка t.me/имя или id -100…. Бот должен быть админом каждого канала: иначе Telegram не скажет, кто подписан. Приватному каналу бот сам сделает ссылку-приглашение."
      >
        <Textarea rows={4} value={channels} onChange={(e) => setChannels(e.target.value)} />
      </Field>
      <Field label="Сколько из них нужно" hint={`0 выключает. Сейчас в списке ${lines.length}.`}>
        <Input
          type="number"
          min={0}
          max={lines.length}
          value={need}
          onChange={(e) => setNeed(Number(e.target.value))}
        />
      </Field>
      <div className="flex items-center gap-3">
        <Button
          size="sm"
          disabled={save.isPending}
          onClick={() => save.mutate({ channels: lines, need })}
        >
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
          Бесплатная Бронза без ИИ, пока человек подписан на нужное число каналов из списка. Даётся, только
          когда у него нет другого тарифа; любая оплата или смена тарифа её заменяет. Бот проверяет подписки
          каждый час: отписался, и план выключается с сообщением и счётом на Relay. Кнопка в /subscription
          видна, пока список не пуст и число больше 0.
        </Hint>
      </div>
      {isLoading || !data ? (
        <Skeleton className="h-24 w-full" />
      ) : (
        <>
          <div className="text-sm text-zinc-400">
            Сейчас действует: {data.grants.running} · за 30 дней включили: {data.grants.started} · выключились:{" "}
            {data.grants.ended}
          </div>
          <Form key={JSON.stringify([data.channels, data.need])} plan={data} />
        </>
      )}
    </Card>
  );
}
