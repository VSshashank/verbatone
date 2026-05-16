import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App.jsx";
import "./styles/app.css";

if (import.meta.env.DEV) {
  const host = window.location.hostname;
  const port = window.location.port || "5173";
  if (host === "localhost" || host === "127.0.0.1") {
    console.log("Access on mobile: https://<your-mac-local-ip>:5173");
    console.log("Find your Mac IP with: ipconfig getifaddr en0");
  } else {
    console.log(`Access on mobile: https://${host}:${port}`);
  }
  console.log("Accept the self-signed cert warning on first visit");
}

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
