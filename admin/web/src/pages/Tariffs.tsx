import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, Tariff } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card, Input, Skeleton } from "@/components/ui/primitives";
import { useState } from "react";

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
      <td className="px-3 py-2">{row.level}</td>
      {(["price", "notify_count", "compression", "channel_control"] as const).map(
        (key) => (
          <td key={key} className="px-2 py-2">
            <Input
              type="number"
              value={draft[key] ?? 0}
              onChange={(e) =>
                setDraft({ ...draft, [key]: Number(e.target.value) })
              }
            />
          </td>
        ),
      )}
      <td className="px-2 py-2">
        <Button
          size="sm"
          disabled={save.isPending}
          onClick={() => save.mutate(draft)}
        >
          {save.isPending ? "…" : "Изменить"}
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
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-bold">Тарифы</h1>
        <p className="text-sm text-zinc-500">Те же поля, что в PHP-таблице.</p>
      </div>
      <Card className="overflow-x-auto p-0">
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
                <th className="px-3 py-3">price (cent)</th>
                <th className="px-3 py-3">notify</th>
                <th className="px-3 py-3">compression</th>
                <th className="px-3 py-3">channel_control</th>
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
