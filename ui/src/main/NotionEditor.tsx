import { useCreateBlockNote } from "@blocknote/react";
import { BlockNoteView } from "@blocknote/mantine";
import "@blocknote/mantine/style.css";
import type { BlockNoteDoc } from "../transport/notionChannel";

export function NotionEditor({ initial, onChange }: { initial: BlockNoteDoc; onChange: (doc: BlockNoteDoc) => void }) {
  const editor = useCreateBlockNote({ initialContent: initial.length ? (initial as any) : undefined });
  return <BlockNoteView editor={editor} onChange={() => onChange(editor.document as any)} />;
}
