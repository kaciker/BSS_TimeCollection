import { useEffect, useRef } from "react";
import type { ReactNode } from "react";

export function EditorDialog({ title, description, busy, onClose, children }: {
  title: string; description: string; busy: boolean; onClose: () => void; children: ReactNode;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => { const dialog = ref.current; dialog?.showModal(); return () => dialog?.close(); }, []);
  return <dialog ref={ref} className="editor-dialog" aria-labelledby="editor-title" onCancel={event => { event.preventDefault(); if (!busy) onClose(); }}>
    <div className="editor-header"><div><div className="eyebrow">CONFIGURATION</div><h2 id="editor-title">{title}</h2><p>{description}</p></div><button className="icon-button" aria-label="Close editor" type="button" disabled={busy} onClick={onClose}>×</button></div>
    {children}
  </dialog>;
}
