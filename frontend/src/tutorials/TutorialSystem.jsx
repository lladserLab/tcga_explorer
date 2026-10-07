import React from "react";
import { TutorialDock } from "./TutorialDock";
import { TutorialLibrary } from "./TutorialLibrary";
import { useTutorialController } from "./useTutorialController";

/** Convenience composition. Integrations may instead render the library and
 * dock separately while sharing one controller instance. */
export function TutorialSystem({
  controllerOptions,
  capabilities,
  triggerRef,
  onNavigate,
  onApplyPreset,
  onPrint,
  libraryClassName = "",
  dockClassName = "",
}) {
  const controller = useTutorialController(controllerOptions);
  return (
    <>
      <TutorialLibrary
        controller={controller}
        className={libraryClassName}
        onPrint={onPrint}
      />
      <TutorialDock
        controller={controller}
        capabilities={capabilities}
        triggerRef={triggerRef}
        className={dockClassName}
        onNavigate={onNavigate}
        onApplyPreset={onApplyPreset}
      />
    </>
  );
}

export default TutorialSystem;
