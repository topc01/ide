import { createRoot } from "react-dom/client";
import App from "./App";
import "./index.css";
import { interceptBlankLinks } from "./lib/openExternal";
interceptBlankLinks();
// un archivo soltado fuera de una zona que lo recibe: el navegador lo abría en otra pestaña (y se perdía el IDE)
for (const ev of ["dragover", "drop"]) {
  window.addEventListener(ev, (e) => { if ((e as DragEvent).dataTransfer?.types.includes("Files")) e.preventDefault(); });
}
createRoot(document.getElementById("root")!).render(<App />);
