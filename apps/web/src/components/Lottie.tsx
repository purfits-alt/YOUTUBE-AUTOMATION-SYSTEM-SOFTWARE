import { useEffect, useRef } from "react";

export type LottieName = "studio-orb" | "empty-box" | "success-check";

const loaders: Record<LottieName, () => Promise<{ default: unknown }>> = {
  "studio-orb": () => import("../assets/lottie/studio-orb.json"),
  "empty-box": () => import("../assets/lottie/empty-box.json"),
  "success-check": () => import("../assets/lottie/success-check.json"),
};

function prefersReducedMotion(): boolean {
  return (
    typeof window.matchMedia === "function" && window.matchMedia("(prefers-reduced-motion: reduce)").matches
  );
}

/**
 * Lottie animation (our own artwork, tools/gen_lottie.py). The player (lottie-web light, MIT) is
 * loaded lazily so it never delays first paint. With "reduce motion" the last frame is shown still.
 */
export function Lottie({
  name,
  loop = true,
  className = "size-24",
}: {
  name: LottieName;
  loop?: boolean;
  className?: string;
}) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let disposed = false;
    let destroy: (() => void) | undefined;
    // jsdom (unit tests) has no SVG layout; skip the player there.
    if (typeof navigator !== "undefined" && navigator.userAgent.includes("jsdom")) return;
    void Promise.all([import("lottie-web/build/player/lottie_light"), loaders[name]()]).then(
      ([player, data]) => {
        const el = ref.current;
        if (disposed || !el) return;
        const reduced = prefersReducedMotion();
        const anim = player.default.loadAnimation({
          container: el,
          renderer: "svg",
          loop: reduced ? false : loop,
          autoplay: !reduced,
          animationData: data.default,
          rendererSettings: { preserveAspectRatio: "xMidYMid meet" },
        });
        if (reduced) anim.addEventListener("DOMLoaded", () => anim.goToAndStop(anim.totalFrames - 1, true));
        destroy = () => anim.destroy();
      },
    );
    return () => {
      disposed = true;
      destroy?.();
    };
  }, [name, loop]);

  return <div ref={ref} aria-hidden="true" data-testid={`lottie-${name}`} className={className} />;
}
