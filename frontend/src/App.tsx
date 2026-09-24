import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AuthProvider } from "./context/AuthContext";
import Layout from "./components/Layout";
import Landing from "./pages/Landing";
import Login from "./pages/auth/Login";
import Register from "./pages/auth/Register";
import Tasks from "./pages/dashboard/Tasks";
import TaskDetail from "./pages/dashboard/TaskDetail";
import Workers from "./pages/dashboard/Workers";
import WorkerDetailPage from "./pages/dashboard/WorkerDetail";
import Metrics from "./pages/dashboard/Metrics";
import ApiKeys from "./pages/dashboard/ApiKeys";
import Overview from "./pages/dashboard/Overview";
import Queues from "./pages/dashboard/Queues";
import Activity from "./pages/dashboard/Activity";
import { ProtectedRoute } from "./components/ProtectedRoute";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 1000 * 60 * 5,
      retry: 1,
    },
  },
});

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/" element={<Landing />} />
            <Route path="/login" element={<Login />} />
            <Route path="/register" element={<Register />} />
            <Route
              path="/app"
              element={
                <ProtectedRoute>
                  <Layout />
                </ProtectedRoute>
              }
            >
              <Route index element={<Navigate to="/app/overview" replace />} />
              <Route path="overview" element={<Overview />} />
              <Route path="tasks" element={<Tasks />} />
              <Route path="tasks/:id" element={<TaskDetail />} />
              <Route path="queues" element={<Queues />} />
              <Route path="workers" element={<Workers />} />
              <Route path="workers/:id" element={<WorkerDetailPage />} />
              <Route path="metrics" element={<Metrics />} />
              <Route path="api-keys" element={<ApiKeys />} />
              <Route path="activity" element={<Activity />} />
            </Route>
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </BrowserRouter>
      </AuthProvider>
    </QueryClientProvider>
  );
}

export default App;
