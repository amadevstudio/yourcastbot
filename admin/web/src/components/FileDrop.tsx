import { useRef, useState } from "react";
import { FileAudio, Image as ImageIcon, Upload, X } from "lucide-react";
import { Hint } from "@/components/ui/primitives";
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
  const total = files.reduce((sum, file) => sum + file.size, 0);

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
      <label
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
          "flex cursor-pointer flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed px-4 py-8 text-center transition-colors",
          over
            ? "border-brand bg-brand/10 text-brand"
            : "border-line bg-ink text-zinc-400 hover:border-brand/50 hover:bg-white/[0.03]",
        )}
      >
        <Upload size={22} />
        <div className="text-sm font-medium text-zinc-200">
          Перетащите файлы сюда или нажмите, чтобы выбрать
        </div>
        <Hint className="max-w-md">
          Картинка уйдёт как фото, звук — как аудио. Несколько файлов
          отправляются одним типом на всю пачку. Nginx режет тело запроса
          на 20 МБ.
        </Hint>
        <input
          ref={inputRef}
          type="file"
          multiple
          accept="image/*,audio/*"
          className="sr-only"
          onChange={(e) => add(e.target.files || [])}
        />
      </label>
      {files.length ? (
        <ul className="space-y-2">
          {files.map((file, index) => {
            const audio = isAudioFile(file);
            const Icon = audio ? FileAudio : ImageIcon;
            return (
              <li
                key={`${file.name}-${file.size}-${file.lastModified}`}
                className="flex items-center gap-3 rounded-lg border border-line bg-ink px-3 py-2"
              >
                <Icon size={16} className="shrink-0 text-brand" />
                <div className="min-w-0 flex-1">
                  <div className="truncate text-sm">{file.name}</div>
                  <div className="text-xs text-zinc-500">
                    {formatBytes(file.size)}
                    {audio ? " · аудио" : " · изображение"}
                  </div>
                </div>
                <button
                  type="button"
                  className="rounded-md p-1 text-zinc-500 hover:bg-white/10 hover:text-zinc-200"
                  onClick={() => removeAt(index)}
                  aria-label={`Убрать ${file.name}`}
                >
                  <X size={16} />
                </button>
              </li>
            );
          })}
        </ul>
      ) : null}
      {files.length ? (
        <div className="flex flex-wrap items-center justify-between gap-3 text-xs text-zinc-500">
          <span>
            {files.length} файл(ов) · {formatBytes(total)}
            {total > 18 * 1024 * 1024
              ? " — слишком много, разбейте на несколько рассылок"
              : ""}
          </span>
        </div>
      ) : null}
      <div className="flex flex-wrap gap-4 text-sm">
        <label className="flex items-center gap-2">
          <input
            type="radio"
            checked={kind === "image"}
            onChange={() => onKindChange("image")}
          />
          Как фото
        </label>
        <label className="flex items-center gap-2">
          <input
            type="radio"
            checked={kind === "audio"}
            onChange={() => onKindChange("audio")}
          />
          Как аудио
        </label>
      </div>
      <Hint>
        Тип можно поправить вручную, если расширение не угадалось. Без файла
        уйдёт обычный текст.
      </Hint>
    </div>
  );
}
