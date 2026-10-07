import React, { useEffect, useId, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { GUIDE_VIDEO_COPY } from "../help/registry";
import { guideVideoUrl } from "./videoRegistry";
import "./tutorials.css";

function VideoPlayer({ guideId, title }) {
  const [failed, setFailed] = useState(false);
  const src = guideVideoUrl(guideId);
  return (
    <div className="trace-guide-video-player">
      <div className="trace-guide-video-toolbar">
        <span>{GUIDE_VIDEO_COPY.silent}</span>
      </div>
      <video key={src} src={src} controls playsInline muted preload="none"
        poster={src.replace(/\.mp4$/, ".jpg")}
        aria-label={`${title}: English`}
        onError={() => setFailed(true)} />
      {failed && <p role="status">{GUIDE_VIDEO_COPY.error}</p>}
      <a href={src} target="_blank" rel="noopener noreferrer">{GUIDE_VIDEO_COPY.open}</a>
    </div>
  );
}

function VideoDialog({ guideId, title, onClose, triggerRef }) {
  const dialogRef = useRef(null);
  const titleId = useId();
  useEffect(() => {
    const dialog = dialogRef.current;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    dialog.showModal();
    return () => {
      document.body.style.overflow = previousOverflow;
      dialog.close();
      triggerRef.current?.focus({ preventScroll: true });
    };
  }, [triggerRef]);
  return createPortal(
    <dialog ref={dialogRef} className="trace-video-dialog" aria-labelledby={titleId}
      onCancel={(event) => { event.preventDefault(); onClose(); }}
      onKeyDown={(event) => {
        if (event.key === "Escape") event.stopPropagation();
        if (event.key !== "Tab") return;
        const controls = event.currentTarget.querySelectorAll("button, video[controls], a[href]");
        const first = controls[0];
        const last = controls[controls.length - 1];
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last?.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first?.focus();
        }
      }}>
      <header>
        <h2 id={titleId}>{title}</h2>
        <button type="button" autoFocus onClick={onClose}>{GUIDE_VIDEO_COPY.close}</button>
      </header>
      <VideoPlayer guideId={guideId} title={title} />
    </dialog>, document.body,
  );
}

export function GuideVideo({ guideId, title }) {
  const [open, setOpen] = useState(false);
  const triggerRef = useRef(null);
  if (!guideVideoUrl(guideId)) return null;
  return (
    <>
      <button ref={triggerRef} type="button" className="trace-guide-video" aria-haspopup="dialog"
        onClick={() => setOpen(true)}>{GUIDE_VIDEO_COPY.watch}</button>
      {open && <VideoDialog guideId={guideId} title={title} triggerRef={triggerRef} onClose={() => setOpen(false)} />}
    </>
  );
}
