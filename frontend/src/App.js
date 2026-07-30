import "@/App.css";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { Toaster } from "sonner";
import { AuthProvider, useAuth } from "@/context/AuthContext";
import Layout from "@/components/Layout";
import Login from "@/pages/Login";
import Dashboard from "@/pages/Dashboard";
import LiveRecognition from "@/pages/LiveRecognition";
import RegisterUser from "@/pages/RegisterUser";
import Users from "@/pages/Users";
import Attendance from "@/pages/Attendance";
import RecognitionHistory from "@/pages/RecognitionHistory";
import UnknownPersons from "@/pages/UnknownPersons";
import Cameras from "@/pages/Cameras";
import Settings from "@/pages/Settings";
import Kiosk from "@/pages/Kiosk";
import Reports from "@/pages/Reports";
import CustomerDetail from "@/pages/CustomerDetail";
import useAlertsPoller from "@/hooks/useAlertsPoller";

function Protected({ children }) {
  const { user, initialized } = useAuth();
  useAlertsPoller(!!user);
  if (!initialized) {
    return (
      <div className="min-h-screen bg-[#0A0A0A] text-white/50 font-mono flex items-center justify-center text-sm">
        Booting Sentinel FR…
      </div>
    );
  }
  if (!user) return <Navigate to="/login" replace />;
  if (user.role !== "admin") {
    return (
      <div className="min-h-screen bg-[#0A0A0A] text-white flex items-center justify-center p-8">
        <div className="max-w-md text-center border border-[#FF3B30]/40 bg-[#FF3B30]/5 rounded-md p-8">
          <div className="text-[10px] font-mono tracking-[0.3em] uppercase text-[#FF3B30]">Access denied</div>
          <div className="font-heading text-2xl mt-3">Admin only</div>
          <p className="text-sm text-white/60 mt-3 font-mono">
            Sentinel FR is restricted to administrators. Contact your super-admin to request access.
          </p>
        </div>
      </div>
    );
  }
  return <Layout>{children}</Layout>;
}

function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/kiosk" element={<Kiosk />} />
      <Route path="/" element={<Protected><Dashboard /></Protected>} />
      <Route path="/live" element={<Protected><LiveRecognition /></Protected>} />
      <Route path="/cameras" element={<Protected><Cameras /></Protected>} />
      <Route path="/register" element={<Protected><RegisterUser /></Protected>} />
      <Route path="/users" element={<Protected><Users /></Protected>} />
      <Route path="/customers/:id" element={<Protected><CustomerDetail /></Protected>} />
      <Route path="/attendance" element={<Protected><Attendance /></Protected>} />
      <Route path="/reports" element={<Protected><Reports /></Protected>} />
      <Route path="/history" element={<Protected><RecognitionHistory /></Protected>} />
      <Route path="/unknowns" element={<Protected><UnknownPersons /></Protected>} />
      <Route path="/settings" element={<Protected><Settings /></Protected>} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <AppRoutes />
        <Toaster
          theme="dark"
          position="top-right"
          toastOptions={{
            style: {
              background: "#121212",
              border: "1px solid rgba(255,255,255,0.1)",
              color: "#fff",
              fontFamily: "JetBrains Mono, monospace",
              fontSize: 12,
            },
          }}
        />
      </AuthProvider>
    </BrowserRouter>
  );
}
