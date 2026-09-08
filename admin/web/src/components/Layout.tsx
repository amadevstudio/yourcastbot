import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { BarChart3, LogOut, Radio, Send, Users } from "lucide-react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";

const links = [
  { to: "/", label: "Статистика", icon: BarChart3 },
  { to: "/users", label: "Пользователи", icon: Users },
  { to: "/send", label: "Рассылка", icon: Send },
  { to: "/tariffs", label: "Тарифы", icon: Radio },
];

async function logoutAndGo(
  navigate: ReturnType<typeof useNavigate>,
) {
  await api.logout();
  navigate("/login");
}

export default function Layout({ mail }: { mail: string }) {
  const navigate = useNavigate();
  return (
    <div className="min-h-screen min-w-0 overflow-x-clip lg:grid lg:grid-cols-[240px_minmax(0,1fr)]">
      <aside className="min-w-0 border-b border-line bg-panel lg:flex lg:min-h-screen lg:flex-col lg:border-b-0 lg:border-r">
        <div className="flex min-w-0 items-center justify-between gap-3 px-4 py-4 sm:px-5">
          <div className="flex min-w-0 items-center gap-3">
            <img src="/app/YC.png" alt="" className="h-10 w-10 shrink-0 rounded-lg" />
            <div className="min-w-0">
              <div className="text-sm font-bold tracking-wide">Yourcast</div>
              <div className="text-xs text-zinc-500">Админка</div>
            </div>
          </div>
          <Button
            className="shrink-0 lg:hidden"
            variant="ghost"
            size="sm"
            onClick={() => logoutAndGo(navigate)}
            aria-label="Выйти"
          >
            <LogOut size={14} />
          </Button>
        </div>
        <nav className="flex min-w-0 flex-wrap gap-1 px-3 pb-3 lg:flex-1 lg:flex-col lg:flex-nowrap">
          {links.map((link) => {
            const Icon = link.icon;
            return (
              <NavLink
                key={link.to}
                to={link.to}
                end={link.to === "/"}
                className={({ isActive }) =>
                  `flex shrink-0 items-center gap-2 whitespace-nowrap rounded-lg px-3 py-2 text-sm ${
                    isActive
                      ? "bg-brand text-brand-fg"
                      : "text-zinc-300 hover:bg-white/5"
                  }`
                }
              >
                <Icon size={16} className="shrink-0" />
                {link.label}
              </NavLink>
            );
          })}
        </nav>
        <div className="hidden items-center justify-between gap-2 px-4 py-4 lg:flex">
          <div className="truncate text-xs text-zinc-500" title={mail}>
            {mail}
          </div>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => logoutAndGo(navigate)}
            aria-label="Выйти"
          >
            <LogOut size={14} />
          </Button>
        </div>
      </aside>
      <main className="min-w-0 px-4 py-6 lg:px-8">
        <Outlet />
      </main>
    </div>
  );
}
