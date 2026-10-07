import React, { useEffect, useState } from "react";
import { apiUrl, authorizedFetch } from "./api";

// Private-dataset artifacts require the dataset token header, which a plain <img src> cannot send
// (the API answers 404). Fetch the image with authorizedFetch and show it through an object URL;
// public results load the same way.
export function useAuthorizedObjectUrl(src) {
  const [state, setState] = useState({ url: null, failed: false });
  useEffect(() => {
    if (!src) {
      setState({ url: null, failed: false });
      return undefined;
    }
    let cancelled = false;
    let objectUrl = null;
    setState({ url: null, failed: false });
    authorizedFetch(apiUrl(src))
      .then((response) => {
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return response.blob();
      })
      .then((blob) => {
        if (cancelled) return;
        objectUrl = URL.createObjectURL(blob);
        setState({ url: objectUrl, failed: false });
      })
      .catch(() => {
        if (!cancelled) setState({ url: null, failed: true });
      });
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [src]);
  return state;
}

export default function AuthorizedImage({ src, alt, className, emptyClassName = "expression-inline-empty" }) {
  const image = useAuthorizedObjectUrl(src);
  if (image.url) return <img className={className} src={image.url} alt={alt} />;
  return <p className={emptyClassName}>{image.failed ? "This plot could not be loaded." : "Loading plot…"}</p>;
}
