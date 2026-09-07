export type AdminUser = { id: number; mail: string };

export type Stats = {
  total: number;
  with_subs: number;
  with_subs_notify: number;
  with_bot_sub: number;
  receive_episodes: number;
  digest_reminder: number;
  blocked: number;
  by_lang: { lang: string; count: number }[];
  updater_channel_id: number;
  max_channel_id: number;
  circle_status: string;
};

export type Sub = { name: string; notify: boolean };

export type BotUser = {
  id: number;
  telegramId: number | string;
  lang: string | null;
  deleted: boolean;
  channels_count: number;
  tariff_id: number | null;
  balance: number | null;
  time_left: number | null;
  time_left_days: number | null;
  notify_count: number | null;
  receives_episodes: boolean;
  subs: Sub[];
};

export type UsersPage = {
  users: BotUser[];
  page: number;
  per_page: number;
  total: number;
  pages: number;
};

export type Tariff = {
  id: number;
  level: number;
  price: number;
  notify_count: number;
  compression: number;
  channel_control: number;
};

export type MailJob = {
  id: number;
  status: string;
  message: string;
  parse_mode: string;
  attachment_type: string;
  to_creator_only: boolean;
  recipients_text: string;
  language: string | null;
  total: number;
  sent: number;
  failed: number;
  skipped: number;
  last_error: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  progress: number;
  created_by: string | null;
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  if (init?.body && !(init.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const res = await fetch(path, { credentials: "include", ...init, headers });
  if (res.status === 401 && !path.endsWith("/login")) {
    throw Object.assign(new Error("auth required"), { status: 401 });
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const data = await res.json();
      detail = data.detail || detail;
    } catch {
      /* ignore */
    }
    throw Object.assign(new Error(detail), { status: res.status });
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export const api = {
  me: () => request<AdminUser>("/api/me"),
  login: (mail: string, password: string) =>
    request<AdminUser>("/api/login", {
      method: "POST",
      body: JSON.stringify({ mail, password }),
    }),
  logout: () => request<{ ok: boolean }>("/api/logout", { method: "POST" }),
  stats: () => request<Stats>("/api/stats"),
  users: (page: number, tgid?: string) => {
    const q = new URLSearchParams({ page: String(page) });
    if (tgid) q.set("tgid", tgid);
    return request<UsersPage>(`/api/users?${q.toString()}`);
  },
  tariffs: () => request<{ tariffs: Tariff[] }>("/api/tariffs"),
  saveTariff: (row: Tariff) =>
    request<Tariff>("/api/tariffs", {
      method: "POST",
      body: JSON.stringify(row),
    }),
  mailJobs: () => request<{ jobs: MailJob[] }>("/api/mail"),
  mailJob: (id: number) => request<MailJob>(`/api/mail/${id}`),
  cancelMail: (id: number) =>
    request<MailJob>(`/api/mail/${id}/cancel`, { method: "POST" }),
  sendMail: (form: FormData) =>
    request<MailJob>("/api/mail", { method: "POST", body: form }),
};
