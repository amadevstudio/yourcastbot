import { useEffect, useRef, useState } from "react";
import { FileAudio, Image as ImageIcon, Upload, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge, Hint } from "@/components/ui/primitives";
import { cn, formatBytes } from "@/lib/utils";

export type AttachmentKind = "image" | "audio";

function isAudioFile(file: File) {
  return (
    file.type.startsWith("audio/") ||
    /\.(mp3|ogg|oga|m4a|wav|flac|aac)$/i.test(file.name)
  );
}

function isImageFile(file: File) {
  return (
    file.type.startsWith("image/") ||
    /\.(jpe?g|png|gif|webp|bmp)$/i.test(file.name)
  );
}

function guessKind(files: File[]): AttachmentKind | null {
  const audio = files.some(isAudioFile);
  const image = files.some(isImageFile);
  if (audio && !image) return "audio";
  if (image && !audio) return "image";
  return null;
}

export function FileDrop({
  files,
  onChange,
  kind,
  onKindChange,
}: {
  files: File[];
  onChange: (files: File[]) => void;
  kind: AttachmentKind;
  onKindChange: (kind: AttachmentKind) => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);
  const [previews, setPreviews] = useState<string[]>([]);
  const total = files.reduce((sum, file) => sum + file.size, 0);

  useEffect(() => {
    const urls = files.map((file) =>
      isImageFile(file) ? URL.createObjectURL(file) : "",
    );
    setPreviews(urls);
    return () => {
      urls.forEach((url) => {
        if (url) URL.revokeObjectURL(url);
      });
    };
  }, [files]);

  function add(list: FileList | File[]) {
    const incoming = Array.from(list);
    if (!incoming.length) return;
    const merged = [...files];
    for (const file of incoming) {
      if (
        merged.some(
          (old) =>
            old.name === file.name &&
            old.size === file.size &&
            old.lastModified === file.lastModified,
        )
      ) {
        continue;
      }
      merged.push(file);
    }
    onChange(merged);
    const guessed = guessKind(merged);
    if (guessed) onKindChange(guessed);
    if (inputRef.current) inputRef.current.value = "";
  }

  function removeAt(index: number) {
    const next = files.filter((_, i) => i !== index);
    onChange(next);
    const guessed = guessKind(next);
    if (guessed) onKindChange(guessed);
  }

  return (
    <div className="space-y-3">
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setOver(true);
        }}
        onDragLeave={() => setOver(false)}
        onDrop={(e) => {
          e.preventDefault();
          setOver(false);
          add(e.dataTransfer.files);
        }}
        className={cn(
          "rounded-lg border bg-ink transition-colors",
          over ? "border-brand ring-2 ring-brand/40" : "border-line",
        )}
      >
        <div className="flex items-center gap-2 p-1.5">
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => inputRef.current?.click()}
          >
            <Upload size={14} />
            Выбрать
          </Button>
          <div className="min-w-0 flex-1 truncate text-sm text-zinc-400">
            {files.length
              ? `${files.length} файл(ов) · ${formatBytes(total)}`
              : "Перетащите сюда или нажмите «Выбрать»"}
          </div>
          {files.length ? (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={() => onChange([])}
            >
              Очистить
            </Button>
          ) : null}
          <input
            ref={inputRef}
            type="file"
            multiple
            accept="image/*,audio/*"
            className="sr-only"
            onChange={(e) => add(e.target.files || [])}
          />
        </div>
      </div>
      {files.length ? (
        <ul className="space-y-2">
          {files.map((file, index) => {
            const audio = isAudioFile(file);
            return (
              <li
                key={`${file.name}-${file.size}-${file.lastModified}`}
                className="flex items-center gap-3 rounded-lg border border-line bg-panel px-3 py-2"
              >
                {previews[index] ? (
                  <img
                    src={previews[index]}
                    alt=""
                    className="h-12 w-12 shrink-0 rounded-md object-cover"
                  />
                ) : (
                  <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-md bg-white/5 text-brand">
                    {audio ? <FileAudio size={18} /> : <ImageIcon size={18} />}
                  </div>
                )}
                <div className="min-w-0 flex-1">
                  <div className="truncate text-sm">{file.name}</div>
                  <div className="mt-0.5 flex flex-wrap items-center gap-2">
                    <span className="text-xs text-zinc-500">
                      {formatBytes(file.size)}
                    </span>
                    <Badge tone="mute">{audio ? "аудио" : "фото"}</Badge>
                  </div>
                </div>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={() => removeAt(index)}
                  aria-label={`Убрать ${file.name}`}
                >
                  <X size={14} />
                </Button>
              </li>
            );
          })}
        </ul>
      ) : null}
      {total > 18 * 1024 * 1024 ? (
        <Hint className="text-red-400">
          Сумма больше 18 МБ — nginx, скорее всего, обрежет запрос. Разбейте
          на несколько рассылок.
        </Hint>
      ) : null}
      <div className="flex flex-wrap gap-2">
        <Button
          type="button"
          size="sm"
          variant={kind === "image" ? "default" : "outline"}
          onClick={() => onKindChange("image")}
        >
          <ImageIcon size={14} />
          Как фото
        </Button>
        <Button
          type="button"
          size="sm"
          variant={kind === "audio" ? "default" : "outline"}
          onClick={() => onKindChange("audio")}
        >
          <FileAudio size={14} />
          Как аудио
        </Button>
      </div>
      <Hint>
        Telegram шлёт всю пачку одним типом. Без файла уйдёт обычный текст.
        Лимит тела запроса — 20 МБ.
      </Hint>
    </div>
  );
}
