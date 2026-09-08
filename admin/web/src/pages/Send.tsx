import { FormEvent, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, MailJob } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { FileDrop, type AttachmentKind } from "@/components/FileDrop";
import {
  Badge,
  Card,
  Field,
  Hint,
  Input,
  Progress,
  Textarea,
} from "@/components/ui/primitives";
import { formatWhen } from "@/lib/utils";

const STATUS: Record<
  string,
  { label: string; tone: "default" | "ok" | "warn" | "mute" }
> = {
  queued: { label: "в очереди", tone: "default" },
  running: { label: "идёт отправка", tone: "default" },
  done: { label: "готово", tone: "ok" },
  failed: { label: "ошибка", tone: "warn" },
  cancelled: { label: "остановлено", tone: "mute" },
  paused: { label: "на паузе", tone: "mute" },
  cancel_requested: { label: "останавливаем…", tone: "mute" },
};

function statusOf(value: string) {
  return STATUS[value] || { label: value, tone: "default" as const };
}

function JobCard({ job }: { job: MailJob }) {
  const queryClient = useQueryClient();
  const cancel = useMutation({
    mutationFn: () => api.cancelMail(job.id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["mail"] }),
  });
  const resume = useMutation({
    mutationFn: () => api.resumeMail(job.id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["mail"] }),
  });
  const live = job.status === "queued" || job.status === "running";
  const status = statusOf(job.status);
  return (
    <Card className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="font-semibold">Задача #{job.id}</div>
        <Badge tone={status.tone}>{status.label}</Badge>
      </div>
      <Progress value={job.progress} />
      <div className="text-sm text-zinc-300 [overflow-wrap:anywhere]">
        отправлено {job.sent} · ошибок {job.failed} · пропущено {job.skipped}
        {" · "}
        осталось {job.remaining ?? Math.max((job.total || 0) - job.sent, 0)} из{" "}
        {job.total || "?"}
      </div>
      <Hint>
        {job.to_creator_only
          ? "Тест только создателю"
          : job.recipients_text
            ? `Список: ${job.recipients_text}`
            : "Всем, кого набрала очередь"}
        {job.language ? ` · язык ${job.language}` : ""}
        {job.created_by ? ` · ${job.created_by}` : ""}
        {job.created_at ? ` · ${formatWhen(job.created_at)}` : ""}
      </Hint>
      {job.last_error ? (
        <div className="text-sm text-red-400 [overflow-wrap:anywhere]">{job.last_error}</div>
      ) : null}
      {job.recent_errors?.length ? (
        <div className="space-y-1 text-xs text-zinc-500 [overflow-wrap:anywhere]">
          {job.recent_errors.map((row, i) => (
            <div key={`${row.tgid}-${i}`}>
              {row.tgid}: {row.error || "ошибка"}
            </div>
          ))}
        </div>
      ) : null}
      <div className="flex flex-wrap gap-2">
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
        {job.can_resume ? (
          <Button
            size="sm"
            disabled={resume.isPending}
            onClick={(e) => {
              e.stopPropagation();
              resume.mutate();
            }}
          >
            Продолжить
          </Button>
        ) : null}
      </div>
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

  const stats = useQuery({
    queryKey: ["stats"],
    queryFn: api.stats,
  });

  const [toCreator, setToCreator] = useState(true);
  const [files, setFiles] = useState<File[]>([]);
  const [kind, setKind] = useState<AttachmentKind>("image");
  const [language, setLanguage] = useState("");
  const [recipients, setRecipients] = useState("");
  const [error, setError] = useState("");

  const allCount = useMemo(() => {
    if (!stats.data) return null;
    const lang = language.trim();
    if (lang) {
      const row = stats.data.by_lang.find((item) => item.lang === lang);
      return row ? row.count : 0;
    }
    return stats.data.total;
  }, [stats.data, language]);

  const listCount = recipients
    .split(",")
    .map((part) => part.trim())
    .filter(Boolean).length;

  const targetCount = toCreator
    ? 1
    : listCount
      ? listCount
      : allCount;

  async function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError("");
    const form = new FormData(e.currentTarget);
    if (!toCreator && !String(form.get("recipients_identifiers") || "").trim()) {
      const n = allCount != null ? String(allCount) : "всем живым";
      const ok = window.confirm(
        `Отправить ${n} живым пользователям?\n\n` +
          "Это не тест создателю. Сообщения идут тем же бот-токеном, что и выпуски: " +
          "Telegram может притормозить и рассылку, и выдачу эпизодов. " +
          "Остановить можно на карточке задачи.",
      );
      if (!ok) return;
    }
    form.set("to_creator_only", toCreator ? "true" : "false");
    form.delete("attachments");
    for (const file of files) {
      form.append("attachments", file);
    }
    if (files.length) {
      form.set("attachment_type", kind);
    } else {
      form.set("attachment_type", "");
    }
    try {
      await send.mutateAsync(form);
      setFiles([]);
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
    <div className="grid min-w-0 gap-6 lg:grid-cols-[minmax(0,1.2fr)_minmax(0,.8fr)]">
      <div className="min-w-0 space-y-4">
        <div className="space-y-1">
          <h1 className="text-2xl font-bold">Рассылка</h1>
          <Hint>
            Сообщение встаёт в очередь фонового воркера. Прогресс справа
            обновляется сам. Рассылка не занимает слоты скачивания выпусков.
          </Hint>
        </div>
        <Card>
          <form className="space-y-4" onSubmit={onSubmit}>
            <Field
              label="Сообщение"
              hint="Текст, который уйдёт в Telegram. Если есть файл — это подпись к первому вложению."
            >
              <Textarea name="message" required />
            </Field>
            <Field
              label="Разметка"
              hint="HTML: <b>, <i>, <a href>, <code>, <pre>. Markdown: *жирный*, _курсив_, `код`. Сломанные теги Telegram не отправит."
            >
              <div className="flex flex-wrap gap-4 text-sm">
                <label className="flex items-center gap-2">
                  <input
                    type="radio"
                    name="parse_mode"
                    value="html"
                    defaultChecked
                  />
                  HTML
                </label>
                <label className="flex items-center gap-2">
                  <input type="radio" name="parse_mode" value="mrkd" />
                  Markdown
                </label>
              </div>
            </Field>
            <Field label="Файлы">
              <FileDrop
                files={files}
                onChange={setFiles}
                kind={kind}
                onKindChange={setKind}
              />
            </Field>
            <label className="flex items-start gap-2 text-sm">
              <input
                className="mt-1"
                type="checkbox"
                checked={toCreator}
                onChange={(e) => setToCreator(e.target.checked)}
              />
              <span>
                Только создателю
                <Hint>
                  Безопасный тест: сообщение уйдёт вам, очередь и вложения
                  проверятся, рассылки по базе не будет.
                </Hint>
              </span>
            </label>
            <Field
              label="Кому ещё"
              hint={
                toCreator
                  ? "Пока включён тест создателю, этот список не используется."
                  : "Telegram id через запятую. Пусто — все живые (не заблокировали бота), с фильтром языка если задан. Не только платники."
              }
            >
              <Textarea
                name="recipients_identifiers"
                className="min-h-[70px]"
                placeholder="123456789, 987654321"
                disabled={toCreator}
                value={recipients}
                onChange={(e) => setRecipients(e.target.value)}
              />
            </Field>
            <Field
              label="Язык"
              hint="Код из профиля, как на статистике: ru, en. Пусто — без фильтра по языку."
            >
              <Input
                name="language"
                placeholder="ru"
                disabled={toCreator}
                value={language}
                onChange={(e) => setLanguage(e.target.value)}
              />
            </Field>
            {!toCreator ? (
              <Hint>
                Уйдёт примерно {targetCount ?? "…"} сообщений
                {listCount
                  ? " по списку id."
                  : language.trim()
                    ? ` с языком «${language.trim()}».`
                    : " всем живым."}{" "}
                Пауза 1 с каждые 50 штук. FloodWait повторяется один раз, дальше
                человек считается ошибкой. Лимит Bot API общий с выдачей выпусков.
                Сначала прогоните тест создателю.
              </Hint>
            ) : null}
            {error ? <p className="text-sm text-red-400">{error}</p> : null}
            <Button type="submit" disabled={send.isPending}>
              {send.isPending ? "Ставим в очередь…" : "Отправить"}
            </Button>
          </form>
        </Card>
      </div>
      <div className="min-w-0 space-y-4">
        {current ? <JobCard job={current} /> : (
          <Hint>После отправки здесь появится прогресс текущей задачи.</Hint>
        )}
        <div className="text-sm font-semibold text-zinc-400">Недавние</div>
        {recent.length ? (
          recent.map((job) => (
            <div
              key={job.id}
              className="cursor-pointer"
              onClick={() => setActiveId(job.id)}
            >
              <JobCard job={job} />
            </div>
          ))
        ) : (
          <Hint>Пока пусто — ни одной рассылки в этой базе.</Hint>
        )}
      </div>
    </div>
  );
}
