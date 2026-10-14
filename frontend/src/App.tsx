import { Suspense, lazy } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import Layout from "./components/Layout";
import { Spinner, ToastProvider } from "./components/ui";
import { AuthProvider, useAuth } from "./hooks/auth";
import { LiveProvider } from "./hooks/live";
import Dashboard from "./pages/Dashboard";
import Login from "./pages/Login";

const Alerts = lazy(() => import("./pages/Alerts"));
const Commands = lazy(() => import("./pages/Commands"));
const Devices = lazy(() => import("./pages/Devices"));
const Events = lazy(() => import("./pages/Events"));
const History = lazy(() => import("./pages/History"));
const ML = lazy(() => import("./pages/ML"));
const RoomDetail = lazy(() => import("./pages/RoomDetail"));
const Rooms = lazy(() => import("./pages/Rooms"));
const Schedules = lazy(() => import("./pages/Schedules"));
const Settings = lazy(() => import("./pages/Settings"));
const Simulation = lazy(() => import("./pages/Simulation"));

function Gate() {
  const { user, token, loading } = useAuth();
  if (loading) return <Spinner label="Checking session" />;
  if (!user) return <Login />;
  return (
    <LiveProvider token={token}>
      <Suspense fallback={<Spinner />}>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<Dashboard />} />
          <Route path="rooms" element={<Rooms />} />
          <Route path="rooms/:id" element={<RoomDetail />} />
          <Route path="devices" element={<Devices />} />
          <Route path="history" element={<History />} />
          <Route path="alerts" element={<Alerts />} />
          <Route path="commands" element={<Commands />} />
          <Route path="schedules" element={<Schedules />} />
          <Route path="ml" element={<ML />} />
          <Route path="simulation" element={<Simulation />} />
          <Route path="events" element={<Events />} />
          <Route path="settings" element={<Settings />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
      </Suspense>
    </LiveProvider>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <ToastProvider>
        <AuthProvider>
          <Gate />
        </AuthProvider>
      </ToastProvider>
    </BrowserRouter>
  );
}
