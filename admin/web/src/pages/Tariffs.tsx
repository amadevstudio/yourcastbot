import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, Tariff } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card, Hint, Input, Skeleton } from "@/components/ui/primitives";
import { centsToUsd } from "@/lib/utils";
import { useState } from "react";

const columns: {
  key: "price" | "notify_count" | "compression" | "channel_control";
  label: string;
  hint: string;
}[] = [
  {
    key: "price",
    label: "Цена, центы",
    hint: "В базе хранится в центах: 199 = $1.99. Бот делит на 100 перед оплатой.",
  },
  {
    key: "notify_count",
    label: "Лимит notify",
    hint: "Сколько выпусков можно получить по тарифу. −1 — без ограничения. 0 — тариф «живой» не считается.",
  },
  {
    key: "compression",
    label: "Compression",
    hint: "Служебный флаг тарифа (0/1). В меню оплаты сейчас не показывается.",
  },
  {
    key: "channel_control",
    label: "Каналы",
    hint: "1 — человеку доступно управление своими каналами в боте. 0 — нет.",
  },
];

function Row({ row }: { row: Tariff }) {
  const queryClient = useQueryClient();
  const [draft, setDraft] = useState(row);
  const save = useMutation({
    mutationFn: api.saveTariff,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["tariffs"] }),
  });
  return (
    <tr className="border-t border-line">
      <td className="px-3 py-2 text-zinc-400">{row.id}</td>
      <td className="px-3 py-2">
        <div>{row.level}</div>
        <div className="text-[11px] text-zinc-500">уровень в боте</div>
      </td>
      {columns.map((col) => (
        <td key={col.key} className="px-2 py-2 align-top">
          <Input
            type="number"
            value={draft[col.key] ?? 0}
            onChange={(e) =>
              setDraft({ ...draft, [col.key]: Number(e.target.value) })
            }
          />
          {col.key === "price" ? (
            <div className="mt-1 text-[11px] text-zinc-500">
              = ${centsToUsd(draft.price)}
            </div>
          ) : null}
          {col.key === "notify_count" && draft.notify_count === -1 ? (
            <div className="mt-1 text-[11px] text-zinc-500">без лимита</div>
          ) : null}
        </td>
      ))}
      <td className="px-2 py-2">
        <Button
          size="sm"
          disabled={save.isPending}
          onClick={() => save.mutate(draft)}
        >
          {save.isPending ? "…" : "Сохранить"}
        </Button>
      </td>
    </tr>
  );
}

export default function Tariffs() {
  const { data, isLoading } = useQuery({
    queryKey: ["tariffs"],
    queryFn: api.tariffs,
  });
  return (
    <div className="min-w-0 space-y-5">
      <div className="space-y-1">
        <h1 className="text-2xl font-bold">Тарифы</h1>
        <Hint>
          Планы подписки на бота. Id и уровень не меняются здесь — только цена
          и флаги. Правка сразу попадает в sqlite, с которой читает бот.
        </Hint>
      </div>
      <div className="grid min-w-0 gap-3 sm:grid-cols-2">
        {columns.map((col) => (
          <Card key={col.key} className="space-y-1 p-4">
            <div className="text-sm font-medium">{col.label}</div>
            <Hint>{col.hint}</Hint>
          </Card>
        ))}
      </div>
      <Card className="max-w-full overflow-x-auto p-0">
        {isLoading || !data ? (
          <div className="space-y-3 p-5">
            <Skeleton className="h-10 w-full" />
            <Skeleton className="h-10 w-full" />
          </div>
        ) : (
          <table className="w-full min-w-[720px] text-sm">
            <thead className="text-left text-zinc-500">
              <tr>
                <th className="px-3 py-3">id</th>
                <th className="px-3 py-3">level</th>
                {columns.map((col) => (
                  <th key={col.key} className="px-3 py-3" title={col.hint}>
                    {col.label}
                  </th>
                ))}
                <th className="px-3 py-3"></th>
              </tr>
            </thead>
            <tbody>
              {data.tariffs.map((row) => (
                <Row key={`${row.id}-${row.level}`} row={row} />
              ))}
            </tbody>
          </table>
        )}
      </Card>
    </div>
  );
}
