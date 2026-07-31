import { NavLink, useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import {
  SquaresFour, VideoCamera, UserPlus, Users as UsersIcon,
  ClockCounterClockwise, Waveform, Warning, SignOut, ShieldCheck,
  Broadcast, GearSix, ChartLine,
} from "@phosphor-icons/react";

const items = [
  { to: "/", label: "Dashboard", icon: SquaresFour, testid: "nav-dashboard" },
  { to: "/live", label: "Live Recognition", icon: VideoCamera, testid: "nav-live" },
  { to: "/cameras", label: "Cameras", icon: Broadcast, testid: "nav-cameras" },
  { to: "/register", label: "Register Customer", icon: UserPlus, testid: "nav-register" },
  { to: "/users", label: "Customers", icon: UsersIcon, testid: "nav-users" },
  { to: "/attendance", label: "Visits", icon: Waveform, testid: "nav-attendance" },
  { to: "/reports", label: "Reports", icon: ChartLine, testid: "nav-reports" },
  { to: "/history", label: "Recognition Log", icon: ClockCounterClockwise, testid: "nav-history" },
  { to: "/unknowns", label: "Unknown Faces", icon: Warning, testid: "nav-unknowns" },
  { to: "/settings", label: "Settings", icon: GearSix, testid: "nav-settings" },
];

export default function Layout({ children }) {
  const { user, logout } = useAuth();
  const nav = useNavigate();

  return (
    <div className="min-h-screen flex bg-[#0A0A0A] text-white">
      <aside className="w-64 shrink-0 border-r border-white/10 bg-[#0A0A0A] flex flex-col">
        <div className="px-6 py-6 border-b border-white/10 flex items-center gap-3">
          <div className="w-9 h-9 rounded-md bg-[#00FF66]/10 border border-[#00FF66]/30 flex items-center justify-center">
            <ShieldCheck size={20} weight="duotone" color="#00FF66" />
          </div>
          <div>
            <div className="font-heading text-sm font-bold tracking-tight">SENTINEL / FR</div>
            <div className="font-mono text-[10px] tracking-[0.2em] text-white/40 uppercase">FACE ENGINE</div>
          </div>
        </div>

        <nav className="flex-1 px-3 py-4 space-y-1">
          {items.map(({ to, label, icon: Icon, testid }) => (
            <NavLink
              key={to}
              to={to}
              end={to === "/"}
              data-testid={testid}
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-2.5 rounded-md text-sm transition-colors duration-150 ${
                  isActive
                    ? "bg-[#00FF66]/10 text-[#00FF66] border border-[#00FF66]/30"
                    : "text-white/70 hover:bg-white/5 hover:text-white border border-transparent"
                }`
              }
            >
              <Icon size={18} weight="duotone" />
              <span className="font-mono tracking-wide">{label}</span>
            </NavLink>
          ))}
        </nav>

        <div className="p-4 border-t border-white/10">
          <div className="flex items-center gap-3 mb-3">
            <div className="w-9 h-9 rounded-full bg-white/5 border border-white/10 flex items-center justify-center font-heading font-bold text-sm">
              {(user?.name || "A").slice(0, 1).toUpperCase()}
            </div>
            <div className="min-w-0">
              <div className="text-sm truncate" data-testid="current-user-name">{user?.name}</div>
              <div className="text-[10px] uppercase tracking-[0.2em] text-white/40 font-mono">{user?.role}</div>
            </div>
          </div>
          <button
            data-testid="logout-btn"
            onClick={async () => { await logout(); nav("/login"); }}
            className="w-full flex items-center justify-center gap-2 px-3 py-2 rounded-md text-xs font-mono uppercase tracking-[0.2em] border border-white/10 text-white/70 hover:bg-white/5 hover:text-white transition-colors"
          >
            <SignOut size={14} /> Sign out
          </button>
        </div>
      </aside>

      <main className="flex-1 min-w-0 overflow-x-hidden">{children}</main>
    </div>
  );
}
