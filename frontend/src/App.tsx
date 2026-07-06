import { Navigate, Route, Routes } from "react-router-dom";
import AnalyticsPage from "./admin/AnalyticsPage";
import ContentPage from "./admin/ContentPage";
import LoginPage from "./admin/LoginPage";
import RequireAuth from "./admin/RequireAuth";
import { AuthProvider } from "./context/AuthContext";
import ChatPage from "./customer/ChatPage";

// Two physically separate route trees (spec §11): "/" is the public customer
// surface, "/admin/*" the authenticated admin surface. Customer code must
// never import from the admin tree.

export default function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/" element={<ChatPage />} />
        <Route path="/admin/login" element={<LoginPage />} />
        <Route
          path="/admin/content"
          element={
            <RequireAuth>
              <ContentPage />
            </RequireAuth>
          }
        />
        <Route
          path="/admin/analytics"
          element={
            <RequireAuth>
              <AnalyticsPage />
            </RequireAuth>
          }
        />
        <Route path="/admin/*" element={<Navigate to="/admin/content" replace />} />
      </Routes>
    </AuthProvider>
  );
}
