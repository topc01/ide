import { Button } from "../components/ui/button";

export function PermissionPrompt({ tool, detail, onDecide }:
  { tool: string; detail: string; onDecide: (allow: boolean) => void }) {
  return (
    <div className="mx-2 flex items-center gap-2 rounded-md border border-border bg-card p-2 text-xs">
      <span className="flex-1">
        ¿Permitir <span className="font-medium text-primary">{tool}</span>?{" "}
        <span className="font-mono text-muted-foreground">{detail}</span>
      </span>
      <Button size="sm" onClick={() => onDecide(true)}>Permitir</Button>
      <Button size="sm" variant="secondary" onClick={() => onDecide(false)}>Denegar</Button>
    </div>
  );
}
