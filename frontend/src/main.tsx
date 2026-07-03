import React from "react";
import ReactDOM from "react-dom/client";
import { App } from "./App";
import { AppProvider } from "./store";
import "./index.css";

// Запрет масштабирования «щипком» в мини-аппе: iOS/WKWebView (Telegram) реагирует
// на pinch системными gesture-событиями даже при user-scalable=no в meta —
// гасим их. Двойной тап-зум отключён через touch-action: manipulation (index.css).
["gesturestart", "gesturechange", "gestureend"].forEach((ev) =>
  document.addEventListener(ev, (e) => e.preventDefault(), { passive: false })
);

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <AppProvider>
      <App />
    </AppProvider>
  </React.StrictMode>
);
