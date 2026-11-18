import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import { BRAND_NAME } from "./brand";
import "./styles/tokens.css";
import "./styles/global.css";

document.title = BRAND_NAME;

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
