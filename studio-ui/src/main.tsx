import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import "./index.css";

// Follow the OS theme until settings load, to avoid a light flash in dark mode.
if (window.matchMedia?.("(prefers-color-scheme: dark)").matches) document.documentElement.classList.add("dark");

const root = document.getElementById("root");
if (!root) throw new Error("Missing #root element");

createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
