import { FormEvent, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, MailJob } from "@/lib/api";
import { Button } from "@/components/ui/button";
import {
  Badge,
  Card,
  Input,
  Label,
  Progress,
  Textarea,
} from "@/components/ui/primitives";

function JobCard({ job }: { job: MailJob }) {
  const cancel = useMutation({ mutationFn: () => api.cancelMail(job.id) });
  const live = job.status === "queued" || job.status === "running";
  return (
    <Card className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="font-semibold">Задача #{job.id}</div>
        <Badge
          tone={
            job.status === "done"
              ? "ok"
              : job.status === "failed" || job.status === "cancelled"
                ? "warn"
                : "default"
          }
        >
          {job.status}
        </Badge>
      </div>
      <Progress value={job.progress} />
      <div className="text-sm text-zinc-400">
        {job.sent}/{job.total || "?"} отправлено · failed {job.failed} · skipped{" "}
        {job.skipped}
      </div>
      {job.last_error ? (
        <div className="text-sm text-red-400">{job.last_error}</div>
      ) : null}
      {live ? (
        <Button
          variant="danger"
          size="sm"
          disabled={cancel.isPending}
          onClick={(e) => {
            e.stopPropagation();
            cancel.mutate();
          }}
        >
          Остановить
        </Button>
      ) : null}
    </Card>
  );
}

export default function Send() {
  const queryClient = useQueryClient();
  const [activeId, setActiveId] = useState<number | null>(null);
  const jobs = useQuery({
    queryKey: ["mail"],
    queryFn: api.mailJobs,
    refetchInterval: 2000,
  });
  const active = useQuery({
    queryKey: ["mail", activeId],
    queryFn: () => api.mailJob(activeId!),
    enabled: activeId != null,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "queued" || status === "running" ? 800 : false;
    },
  });
  const send = useMutation({
    mutationFn: api.sendMail,
    onSuccess: (job) => {
      setActiveId(job.id);
      queryClient.invalidateQueries({ queryKey: ["mail"] });
    },
  });

  const [toCreator, setToCreator] = useState(true);
  const [error, setError] = useState("");

  async function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError("");
    const form = new FormData(e.currentTarget);
    if (!toCreator && !String(form.get("recipients_identifiers") || "").trim()) {
      const ok = window.confirm(
        "Отправить всем пользователям? Это не тест создателю.",
      );
      if (!ok) return;
    }
    form.set("to_creator_only", toCreator ? "true" : "false");
    try {
      await send.mutateAsync(form);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не отправилось");
    }
  }

  const current = active.data;
  const recent = useMemo(
    () => (jobs.data?.jobs || []).slice(0, 8),
    [jobs.data],
  );

  return (
    <div className="grid gap-6 lg:grid-cols-[1.2fr_.8fr]">
      <div className="space-y-4">
        <div>
          <h1 className="text-2xl font-bold">Рассылка</h1>
          <p className="text-sm text-zinc-500">
            Больше не скрипт до падения: задача встаёт в очередь jobs-воркера,
            прогресс обновляется здесь.
          </p>
        </div>
        <Card>
          <form className="space-y-4" onSubmit={onSubmit}>
            <div className="space-y-1">
              <Label>Сообщение</Label>
              <Textarea name="message" required />
            </div>
            <div className="flex flex-wrap gap-4 text-sm">
              <label className="flex items-center gap-2">
                <input type="radio" name="parse_mode" value="html" defaultChecked />
                HTML
              </label>
              <label className="flex items-center gap-2">
                <input type="radio" name="parse_mode" value="mrkd" />
                Markdown
              </label>
            </div>
            <div className="space-y-1">
              <Label>Файл</Label>
              <Input type="file" name="attachments" multiple />
            </div>
            <div className="flex flex-wrap gap-4 text-sm">
              <label className="flex items-center gap-2">
                <input
                  type="radio"
                  name="attachment_type"
                  value="image"
                  defaultChecked
                />
                Изображение
              </label>
              <label className="flex items-center gap-2">
                <input type="radio" name="attachment_type" value="audio" />
                Аудио
              </label>
            </div>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={toCreator}
                onChange={(e) => setToCreator(e.target.checked)}
              />
              Только создателю (безопасный тест)
            </label>
            <div className="space-y-1">
              <Label>Telegram id через запятую (пусто — всем)</Label>
              <Textarea
                name="recipients_identifiers"
                className="min-h-[70px]"
                placeholder="123,456"
              />
            </div>
            <div className="space-y-1">
              <Label>Язык (пусто — все)</Label>
              <Input name="language" placeholder="ru" />
            </div>
            {error ? <p className="text-sm text-red-400">{error}</p> : null}
            <Button type="submit" disabled={send.isPending}>
              {send.isPending ? "Ставим в очередь…" : "Отправить"}
            </Button>
          </form>
        </Card>
        <Card className="text-xs leading-5 text-zinc-500">
          HTML: b, i, a, code, pre. Markdown: *bold*, _italic_, `code`.
        </Card>
      </div>
      <div className="space-y-4">
        {current ? <JobCard job={current} /> : null}
        <div className="text-sm font-semibold text-zinc-400">Недавние</div>
        {recent.map((job) => (
          <div
            key={job.id}
            className="cursor-pointer"
            onClick={() => setActiveId(job.id)}
          >
            <JobCard job={job} />
          </div>
        ))}
      </div>
    </div>
  );
}
