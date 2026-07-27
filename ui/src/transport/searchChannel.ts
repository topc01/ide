import type { WsClient } from "./ws";
import type { SearchResult } from "../state/store";

function splitGlobs(s: string): string[] {
  return s.split(/[,\s]+/).map((x) => x.trim()).filter(Boolean);
}

export interface SearchArgs {
  regex: boolean; caseSensitive: boolean; wholeWord: boolean;
  include: string; exclude: string; context: number;
}

export function searchContent(ws: WsClient, sessionId: string, query: string, a: SearchArgs): Promise<SearchResult> {
  return ws.request("search.content", {
    sessionId, query,
    options: {
      regex: a.regex, caseSensitive: a.caseSensitive, wholeWord: a.wholeWord,
      include: splitGlobs(a.include), exclude: splitGlobs(a.exclude), context: a.context,
    },
  });
}
