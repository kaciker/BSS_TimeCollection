import React from "react";
import ReactDOM from "react-dom/client";
import { AdminPage } from "./pages/AdminPage";
import { TerminalPage } from "./pages/TerminalPage";
import "./styles.css";
import "./admin.css";

const isAdmin = window.location.pathname.startsWith("/admin");

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>{isAdmin ? <AdminPage /> : <TerminalPage />}</React.StrictMode>,
);
