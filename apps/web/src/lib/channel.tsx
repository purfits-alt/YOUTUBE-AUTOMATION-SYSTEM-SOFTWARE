import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { useChannels } from "./useBackend";

/** The channel chosen in the top bar; channel pages (/channels/:id/…) in the navigation follow it. */
interface ChannelCtx {
  channelId: string | undefined;
  setChannelId: (id: string) => void;
}

const Ctx = createContext<ChannelCtx>({ channelId: undefined, setChannelId: () => undefined });
const KEY = "tf-channel";

function readStored(): string | undefined {
  try {
    return localStorage.getItem(KEY) ?? undefined;
  } catch {
    return undefined;
  }
}

export function ChannelProvider({ children }: { children: ReactNode }) {
  const channels = useChannels();
  const [chosen, setChosen] = useState<string | undefined>(readStored);
  const items = channels.data?.items ?? [];
  // Fall back to the first channel when the stored one no longer exists.
  const channelId = items.some((c) => c.id === chosen) ? chosen : items[0]?.id;
  useEffect(() => {
    if (!channelId) return;
    try {
      localStorage.setItem(KEY, channelId);
    } catch {
      /* private mode: remember for this tab only */
    }
  }, [channelId]);
  const value = useMemo(() => ({ channelId, setChannelId: setChosen }), [channelId]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useSelectedChannel(): ChannelCtx {
  return useContext(Ctx);
}
