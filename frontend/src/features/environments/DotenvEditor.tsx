import { type KeyboardEvent, useEffect, useRef, useState } from "react";
import { ErrorNote, Spinner } from "../../app/ErrorNote";
import { ApiError } from "../../lib/api";
import { errorMessage } from "../../lib/messages";
import type { DotenvError, ImportResult } from "../../lib/types";
import { type EnvPaths, useDotenv, useSaveDotenv } from "./queries";

function summarize(result: ImportResult): string {
  const n = (status: string) => result.items.filter((i) => i.status === status).length;
  const parts = [
    n("new") && `${n("new")} added`,
    n("changed") && `${n("changed")} changed`,
    n("deleted") && `${n("deleted")} deleted`,
  ].filter(Boolean);
  return parts.length ? parts.join(", ") : "no changes";
}

/**
 * The folder's .env of one environment as plain text. Saving replaces the
 * folder's variables with the document: new keys are added (as secrets),
 * changed ones updated, missing ones deleted, in a single revision.
 */
export function DotenvEditor({
  paths,
  canWrite,
  onDirtyChange,
}: {
  paths: EnvPaths;
  canWrite: boolean;
  onDirtyChange: (dirty: boolean) => void;
}) {
  const doc = useDotenv(paths, true);
  const save = useSaveDotenv(paths);
  const [draft, setDraft] = useState<string | null>(null);
  const [saved, setSaved] = useState<string | null>(null);
  const gutter = useRef<HTMLPreElement>(null);

  const original = doc.data?.text ?? "";
  const text = draft ?? original;
  const dirty = draft !== null && draft !== original;

  useEffect(() => onDirtyChange(dirty), [dirty, onDirtyChange]);

  if (doc.isPending) return <Spinner />;
  if (doc.error) return <ErrorNote>{errorMessage(doc.error)}</ErrorNote>;

  const parseErrors =
    save.error instanceof ApiError && save.error.code === "invalid_dotenv"
      ? (save.error.data.errors as DotenvError[])
      : null;
  const conflict = save.error instanceof ApiError && save.error.code === "revision_conflict";
  const lineCount = text.split("\n").length;
  const fileName = paths.folder ? `${paths.folder}/.env` : ".env";

  function submit() {
    if (!dirty || save.isPending) return;
    setSaved(null);
    save.mutate(
      { content: text, revision: doc.data?.revision ?? "" },
      {
        onSuccess: (result) => {
          setSaved(summarize(result));
          setDraft(null);
        },
      },
    );
  }

  function onKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") {
      e.preventDefault();
      submit();
    }
  }

  return (
    <div className="space-y-3">
      <div className="card overflow-hidden">
        <div className="flex max-h-[65vh] min-h-72 overflow-hidden">
          <pre
            ref={gutter}
            aria-hidden="true"
            className="select-none overflow-hidden border-r border-zinc-100 bg-zinc-50 px-2 py-2.5 text-right font-mono text-xs leading-5 text-zinc-400"
          >
            {Array.from({ length: lineCount }, (_, i) => i + 1).join("\n")}
          </pre>
          <textarea
            aria-label={`${fileName} contents`}
            className="min-w-0 flex-1 resize-none overflow-auto whitespace-pre bg-white px-3 py-2.5 font-mono text-xs leading-5 outline-none"
            wrap="off"
            spellCheck={false}
            autoComplete="off"
            readOnly={!canWrite}
            placeholder={canWrite ? "DATABASE_URL=postgres://...\nAPI_KEY=..." : ""}
            value={text}
            onChange={(e) => {
              setDraft(e.target.value);
              setSaved(null);
              if (save.error && !conflict) save.reset();
            }}
            onScroll={(e) => {
              if (gutter.current) gutter.current.scrollTop = e.currentTarget.scrollTop;
            }}
            onKeyDown={onKeyDown}
          />
        </div>
      </div>

      {parseErrors ? (
        <ErrorNote>
          <p className="font-medium">{errorMessage(save.error)}</p>
          <ul className="mt-1 list-disc pl-5">
            {parseErrors.map((e) => (
              <li key={`${e.line}-${e.code}`}>
                {e.line > 0 ? `Line ${e.line}: ` : ""}
                {e.message}
              </li>
            ))}
          </ul>
        </ErrorNote>
      ) : (
        save.error && <ErrorNote>{errorMessage(save.error)}</ErrorNote>
      )}
      {saved && (
        <p className="rounded-md border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-800">
          Saved: {saved}.
        </p>
      )}

      {canWrite && (
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            className="btn-primary"
            disabled={!dirty || save.isPending}
            onClick={submit}
          >
            {save.isPending ? "Saving…" : "Save"}
          </button>
          {dirty && (
            <button
              type="button"
              className="btn-secondary"
              onClick={() => {
                setDraft(null);
                save.reset();
              }}
            >
              Cancel
            </button>
          )}
          {conflict && (
            <button
              type="button"
              className="btn-secondary"
              onClick={() => {
                if (window.confirm("Discard your draft and load the latest version?")) {
                  setDraft(null);
                  save.reset();
                  doc.refetch();
                }
              }}
            >
              Load latest version
            </button>
          )}
          <p className="text-xs text-zinc-500">
            Press Ctrl+S to save. Keys missing from the file are deleted; new keys are added as
            secrets. Comments and line order are not kept; keys are sorted alphabetically.
          </p>
        </div>
      )}
    </div>
  );
}
