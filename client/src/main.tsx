import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import { ModelPreferenceProvider } from "./context/ModelPreferenceContext";
import "./index.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
      <ModelPreferenceProvider>
        <App />
      </ModelPreferenceProvider>
    </BrowserRouter>
  </StrictMode>,
);
