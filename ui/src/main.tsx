import { createRoot } from "react-dom/client";
import App from "./App";
import "./index.css";
import { interceptBlankLinks } from "./lib/openExternal";
interceptBlankLinks();
createRoot(document.getElementById("root")!).render(<App />);
