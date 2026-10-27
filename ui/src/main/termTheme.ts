import type { ITheme } from "@xterm/xterm";
import type { Theme } from "../state/theme";

/** Colores de xterm según el tema del IDE. En claro, "blanco" queda gris oscuro: los programas lo usan
 *  como texto pensando en fondo negro. Lo que pinta con RGB directo (como `claude`) no pasa por acá:
 *  eso lo decide su propio tema (`/theme`). */
export function termTheme(t: Theme, cursor = true): ITheme {
  if (t === "dark") {
    return { background: "#0f0e0c", foreground: "#f0ece4", cursor: cursor ? "#e0863f" : "#0f0e0c" };
  }
  return {
    background: "#fbf9f4", foreground: "#26231e", cursor: cursor ? "#b9611f" : "#fbf9f4",
    selectionBackground: "#e7d3bb",
    black: "#26231e", red: "#b4472b", green: "#4c7a2a", yellow: "#8a6500", blue: "#2f5f9e",
    magenta: "#8e3fa0", cyan: "#1f767c", white: "#5c564b",
    brightBlack: "#756d5f", brightRed: "#c9552f", brightGreen: "#5a8f33", brightYellow: "#9c7400",
    brightBlue: "#3b6fb5", brightMagenta: "#a24bb5", brightCyan: "#268a90", brightWhite: "#26231e",
  };
}
