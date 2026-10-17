import { Database } from "lucide-react";
import { registerModule } from "../registry";
import { DbPanel } from "./DbPanel";

registerModule({ id: "db", title: "Base de datos", icon: Database, Panel: DbPanel });
