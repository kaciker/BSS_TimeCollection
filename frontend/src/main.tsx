import React from "react";
import ReactDOM from "react-dom/client";
import { AdminAuthGate } from "./components/AdminAuthGate";
import { AdminPage } from "./pages/AdminPage";
import { TerminalPage } from "./pages/TerminalPage";
import "./styles.css";
import "./admin.css";
import "./adminAuth.css";

const isAdmin = window.location.pathname.startsWith("/admin");

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    {isAdmin ? <AdminAuthGate><AdminPage /></AdminAuthGate> : <TerminalPage />}
  </React.StrictMode>,
);
