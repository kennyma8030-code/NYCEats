import { useEffect, useState } from "react";
import { PHONE } from "../lib/layout";

const read = () => ({ width: window.innerWidth, height: window.innerHeight, phone: window.innerWidth <= PHONE });

/** The window's size, for what CSS cannot do alone: sizing the city's panels
 *  to it (lib/layout.ts) and telling the map how much of itself they cover. */
export function useViewport() {
  const [size, setSize] = useState(read);
  useEffect(() => {
    const onResize = () => setSize(read());
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);
  return size;
}
