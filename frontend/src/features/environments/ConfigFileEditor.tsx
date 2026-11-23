import { type KeyboardEvent, useEffect, useRef, useState } from "react";
import { ErrorNote, Spinner } from "../../app/ErrorNote";
import { ApiError } from "../../lib/api";
import { errorMessage } from "../../lib/messages";
import { filePath } from "../projects/ProjectTree";
import { downloadText, type EnvPaths, useConfigFile, useSaveConfigFile } from "./queries";

/**
 * A config file (application.properties, config.json, ...) of one
 * environment as plain text. It is stored exactly as written, encrypted;
 * saving replaces the whole file as one revision.
 */
export function ConfigFileEditor({
  paths,
  name,
  canWrite,
  onDirtyChange,
}: {
  paths: EnvPaths;
  name: string;
  canWrite: boolean;
  onDirtyChange: (dirty: boolean) => void;
}) {
  const doc = useConfigFile(paths, name);
  const save = useSaveConfigFile(paths, name);
  const [draft, setDraft] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const gutter = useRef<HTMLPreElement>(null);

  const original = doc.data?.text ?? "";
  const text = draft ?? original;
  const dirty = draft !== null && draft !== original;

  useEffect(() => onDirtyChange(dirty), [dirty, onDirtyChange]);

  if (doc.isPending) return <Spinner />;
  if (doc.error) return <ErrorNote>{errorMessage(doc.error)}</ErrorNote>;

  const conflict = save.error instanceof ApiError && save.error.code === "revision_conflict";
  const lineCount = text.split("\n").length;
  const fullName = filePath(paths.folder, name);

  function submit() {
    if (!dirty || save.isPending) return;
    setSaved(false);
    save.mutate(
      { content: text, revision: doc.data?.revision ?? "" },
      {
        // The environment's queries (this file's included) are reloaded.
        onSuccess: () => {
          setSaved(true);
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
            aria-label={`${fullName} contents`}
            className="min-w-0 flex-1 resize-none overflow-auto whitespace-pre bg-white px-3 py-2.5 font-mono text-xs leading-5 outline-none"
            wrap="off"
            spellCheck={false}
            autoComplete="off"
            readOnly={!canWrite}
            placeholder={canWrite ? `Contents of ${name} in this environment` : "(empty)"}
            value={text}
            onChange={(e) => {
              setDraft(e.target.value);
              setSaved(false);
              if (save.error && !conflict) save.reset();
            }}
            onScroll={(e) => {
              if (gutter.current) gutter.current.scrollTop = e.currentTarget.scrollTop;
            }}
            onKeyDown={onKeyDown}
          />
        </div>
      </div>

      {save.error && <ErrorNote>{errorMessage(save.error)}</ErrorNote>}
      {saved && (
        <p className="rounded-md border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-800">
          Saved {fullName}.
        </p>
      )}

      <div className="flex flex-wrap items-center gap-2">
        {canWrite && (
          <button
            type="button"
            className="btn-primary"
            disabled={!dirty || save.isPending}
            onClick={submit}
          >
            {save.isPending ? "Saving…" : "Save"}
          </button>
        )}
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
        <button
          type="button"
          className="btn-secondary"
          disabled={dirty}
          title={dirty ? "Save or cancel your changes first" : undefined}
          onClick={() => downloadText(original, name)}
        >
          Download
        </button>
        {canWrite && (
          <p className="text-xs text-zinc-500">
            Press Ctrl+S to save. The file is stored exactly as written (up to 256 KB) and only
            in this environment; saving it empty clears it.
          </p>
        )}
      </div>
    </div>
  );
}
