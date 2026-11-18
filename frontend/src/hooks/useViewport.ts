import { useEffect, useState } from "react";

/** Below this the panel is a sheet over the bottom of the map (the styles use the same width). */
const PHONE = 720;

const read = () => ({ width: window.innerWidth, height: window.innerHeight, phone: window.innerWidth <= PHONE });

/** The window's size, for the one thing CSS cannot do: telling the map how
 *  much of itself the panel covers. */
export function useViewport() {
  const [size, setSize] = useState(read);
  useEffect(() => {
    const onResize = () => setSize(read());
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);
  return size;
}
