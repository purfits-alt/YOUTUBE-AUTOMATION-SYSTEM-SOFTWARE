import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useId, useState } from "react";
import { Link } from "react-router";
import { JobProgress } from "../../components/JobProgress";
import { ProblemDisplay } from "../../components/ProblemDisplay";
import { useToast } from "../../components/Toasts";
import { Badge, Button, Card } from "../../components/ui";
import { t } from "../../i18n";
import { api, call, idempotencyKey } from "../../lib/api/client";
import type { components } from "../../lib/api/schema";
import { asProblem, LoadingSkeleton } from "../PageView";
import { inputCls, problemText } from "./common";

type ChannelArtOut = components["schemas"]["ChannelArtOut"];
type ArtOut = components["schemas"]["ArtOut"];

/** Banner areas YouTube shows (2560 × 1440 canvas): desktop is a centre strip, phone the centre 1546 × 423. */
const DESKTOP = { left: 0, top: 508 / 1440, width: 1, height: 423 / 1440 };
const PHONE = { left: 507 / 2560, top: 508 / 1440, width: 1546 / 2560, height: 423 / 1440 };

function pct(n: number): string {
  return `${String(Math.round(n * 1000) / 10)}%`;
}

export function useChannelArt(channelId: string) {
  return useQuery({
    queryKey: ["channel-art", channelId],
    queryFn: () =>
      call(() =>
        api.GET("/api/v1/channels/{channel_id}/channel-art", { params: { path: { channel_id: channelId } } }),
      ),
    refetchInterval: (q) =>
      q.state.data?.job && ["QUEUED", "RUNNING"].includes(q.state.data.job.status) ? 2000 : false,
  });
}

/** "Copy image" where the browser allows it (Chromium/Edge with the async clipboard). */
const canCopyImage = typeof window !== "undefined" && "ClipboardItem" in window && !!navigator.clipboard;

function ArtActions({ art, label }: { art: ArtOut; label: string }) {
  const toast = useToast();
  const copy = async () => {
    try {
      const blob = await (await fetch(art.download_url, { credentials: "same-origin" })).blob();
      await navigator.clipboard.write([new ClipboardItem({ [blob.type || "image/png"]: blob })]);
      toast(t("channelArt.copied", { what: label }));
    } catch {
      toast(t("channelArt.copyFailed"), "danger");
    }
  };
  return (
    <span className="flex flex-wrap gap-2">
      <a
        className="inline-flex items-center rounded-lg border border-line px-3 py-1.5 text-sm font-medium hover:border-accent"
        href={art.download_url}
        download
      >
        {t("channelArt.download")}
      </a>
      {canCopyImage && <Button onClick={() => void copy()}>{t("channelArt.copy")}</Button>}
    </span>
  );
}

function LogoCard({ art, onPick, name }: { art: ArtOut; onPick: () => void; name: string }) {
  const label = t("channelArt.logoN", { n: art.variant });
  return (
    <li className="space-y-2 rounded-xl border border-line p-3" data-testid={`logo-${String(art.variant)}`}>
      <div className="flex items-center gap-3">
        <img
          src={art.download_url}
          alt={t("channelArt.logoAlt", { name, n: art.variant })}
          className="size-28 rounded-lg"
        />
        <img
          src={art.download_url}
          alt=""
          aria-hidden="true"
          title={t("channelArt.circle")}
          className="size-16 rounded-full border border-line"
        />
      </div>
      <p className="flex flex-wrap items-center gap-2 text-sm">
        <span className="font-medium">{label}</span>
        <span className="text-muted">{art.style}</span>
        {art.chosen && <Badge tone="ok">{t("channelArt.chosen")}</Badge>}
      </p>
      <span className="flex flex-wrap gap-2">
        <Button variant={art.chosen ? "secondary" : "primary"} aria-pressed={art.chosen} onClick={onPick}>
          {art.chosen ? t("channelArt.picked") : t("channelArt.pick")}
        </Button>
        <ArtActions art={art} label={label} />
      </span>
    </li>
  );
}

function BannerCard({ art, onPick, name }: { art: ArtOut; onPick: () => void; name: string }) {
  const label = t("channelArt.bannerN", { n: art.variant });
  const box = (b: typeof DESKTOP, tone: string, text: string) => (
    <span
      className={`pointer-events-none absolute border-2 border-dashed ${tone}`}
      style={{ left: pct(b.left), top: pct(b.top), width: pct(b.width), height: pct(b.height) }}
    >
      <span className="absolute -top-5 left-1 rounded bg-black/70 px-1 text-[10px] text-white">{text}</span>
    </span>
  );
  return (
    <li className="space-y-2 rounded-xl border border-line p-3" data-testid={`banner-${String(art.variant)}`}>
      <div className="relative">
        <img
          src={art.download_url}
          alt={t("channelArt.bannerAlt", { name, n: art.variant })}
          className="block w-full rounded-lg"
        />
        {box(DESKTOP, "border-sky-400", t("channelArt.desktop"))}
        {box(PHONE, "border-amber-400", t("channelArt.phone"))}
      </div>
      <p className="flex flex-wrap items-center gap-2 text-sm">
        <span className="font-medium">{label}</span>
        <span className="text-muted">{art.style}</span>
        {art.chosen && <Badge tone="ok">{t("channelArt.chosen")}</Badge>}
      </p>
      <span className="flex flex-wrap gap-2">
        <Button variant={art.chosen ? "secondary" : "primary"} aria-pressed={art.chosen} onClick={onPick}>
          {art.chosen ? t("channelArt.picked") : t("channelArt.pick")}
        </Button>
        <ArtActions art={art} label={label} />
      </span>
    </li>
  );
}

function WatermarkBox({ channelId, data }: { channelId: string; data: ChannelArtOut }) {
  const toast = useToast();
  const qc = useQueryClient();
  const id = useId();
  const [file, setFile] = useState<File | null>(null);
  const [owned, setOwned] = useState(false);
  const upload = async () => {
    if (!file) return;
    try {
      await call(() =>
        api.POST("/api/v1/channels/{channel_id}/watermark", {
          params: { path: { channel_id: channelId }, query: { confirm_owned: owned } },
          headers: { "Idempotency-Key": idempotencyKey(), "Content-Type": file.type || "image/png" },
          body: file as unknown as string,
          bodySerializer: (b: unknown) => b as BodyInit,
        }),
      );
      toast(t("channelArt.uploading"));
      setFile(null);
      void qc.invalidateQueries({ queryKey: ["channel-art", channelId] });
    } catch (e) {
      toast(problemText(e), "danger");
    }
  };
  const mark = data.watermark;
  return (
    <div className="space-y-2" data-testid="watermark">
      <h3 className="text-sm font-semibold">{t("channelArt.watermark")}</h3>
      <p className="text-xs text-muted">{t("channelArt.watermarkHint")}</p>
      {mark && (
        <div className="flex flex-wrap items-center gap-3">
          <img
            src={mark.download_url}
            alt={t("channelArt.watermarkAlt")}
            className="size-[75px] rounded border border-line bg-[repeating-conic-gradient(#ccc_0_25%,#fff_0_50%)] bg-[length:16px_16px]"
          />
          <ArtActions art={mark} label={t("channelArt.watermark")} />
        </div>
      )}
      <div className="flex flex-wrap items-end gap-3">
        <div>
          <label htmlFor={`${id}-file`} className="block text-sm font-medium">
            {t("channelArt.logoFile")}
          </label>
          <input
            id={`${id}-file`}
            type="file"
            accept="image/png,image/jpeg,image/webp"
            className={inputCls}
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          />
        </div>
        <label className="flex items-center gap-2 pb-2 text-sm">
          <input type="checkbox" checked={owned} onChange={(e) => setOwned(e.target.checked)} />
          {t("channelArt.confirmOwned")}
        </label>
        <Button variant="primary" disabled={!file || !owned} onClick={() => void upload()}>
          {mark ? t("channelArt.replaceWatermark") : t("channelArt.makeWatermark")}
        </Button>
      </div>
    </div>
  );
}

/** Branding Studio › Channel art: draw, pick, download/copy; the owner uploads them in YouTube Studio. */
export function ChannelArtPanel({ channelId }: { channelId: string }) {
  const toast = useToast();
  const qc = useQueryClient();
  const art = useChannelArt(channelId);
  const [tagline, setTagline] = useState("");
  const id = useId();
  const data = art.data;
  const busy = !!data?.job && ["QUEUED", "RUNNING"].includes(data.job.status);
  const generate = async () => {
    try {
      await call(() =>
        api.POST("/api/v1/channels/{channel_id}/channel-art/generate", {
          params: { path: { channel_id: channelId } },
          headers: { "Idempotency-Key": idempotencyKey() },
          body: tagline.trim() ? { tagline: tagline.trim() } : {},
        }),
      );
      toast(t("channelArt.queued"));
      void qc.invalidateQueries({ queryKey: ["channel-art", channelId] });
    } catch (e) {
      toast(problemText(e), "danger");
    }
  };
  const pick = async (a: ArtOut) => {
    try {
      const out = await call(() =>
        api.POST("/api/v1/channels/{channel_id}/channel-art/{art_id}/choose", {
          params: { path: { channel_id: channelId, art_id: a.id } },
        }),
      );
      qc.setQueryData(["channel-art", channelId], out);
      toast(
        t("channelArt.pickedToast", {
          what:
            a.role === "LOGO"
              ? t("channelArt.logoN", { n: a.variant })
              : t("channelArt.bannerN", { n: a.variant }),
        }),
      );
    } catch (e) {
      toast(problemText(e), "danger");
    }
  };
  return (
    <Card title={t("channelArt.title")}>
      <section id="channel-art" data-testid="channel-art" className="space-y-4">
        <p className="text-sm text-muted">{t("channelArt.intro")}</p>
        {art.isPending && <LoadingSkeleton />}
        {art.isError && <ProblemDisplay problem={asProblem(art.error)} onRetry={() => void art.refetch()} />}
        {data && (
          <>
            {!data.blueprint ? (
              <p className="text-sm">{t("channelArt.noBlueprint")}</p>
            ) : (
              <div className="flex flex-wrap items-end gap-3">
                <div className="min-w-0 flex-1">
                  <label htmlFor={`${id}-tagline`} className="block text-sm font-medium">
                    {t("channelArt.tagline")}
                  </label>
                  <input
                    id={`${id}-tagline`}
                    className={inputCls}
                    maxLength={90}
                    value={tagline}
                    placeholder={data.blueprint.default_tagline}
                    onChange={(e) => setTagline(e.target.value)}
                  />
                </div>
                <Button variant="primary" disabled={busy} onClick={() => void generate()}>
                  {data.logos.length ? t("channelArt.again") : t("channelArt.generate")}
                </Button>
              </div>
            )}
            {data.job && (
              <div className="max-w-xl">
                <JobProgress job={data.job} />
              </div>
            )}
            {data.logos.length > 0 && (
              <div>
                <h3 className="text-sm font-semibold">{t("channelArt.logos")}</h3>
                <p className="text-xs text-muted">{t("channelArt.logosHint")}</p>
                <ul className="mt-2 grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
                  {data.logos.map((a) => (
                    <LogoCard key={a.id} art={a} name={data.channel_name} onPick={() => void pick(a)} />
                  ))}
                </ul>
              </div>
            )}
            {data.banners.length > 0 && (
              <div>
                <h3 className="text-sm font-semibold">{t("channelArt.banners")}</h3>
                <p className="text-xs text-muted">{t("channelArt.bannersHint")}</p>
                <ul className="mt-2 grid gap-3 lg:grid-cols-2">
                  {data.banners.map((a) => (
                    <BannerCard key={a.id} art={a} name={data.channel_name} onPick={() => void pick(a)} />
                  ))}
                </ul>
              </div>
            )}
            <WatermarkBox channelId={channelId} data={data} />
            <p className="rounded-lg bg-info-soft px-3 py-2 text-sm text-info-text">
              {t("channelArt.howTo")}
            </p>
          </>
        )}
      </section>
    </Card>
  );
}

/** The setup kit (onboarding step 2): the chosen logo, banner and watermark, ready to download. */
export function ChosenArt({ channelId }: { channelId: string }) {
  const art = useChannelArt(channelId);
  const data = art.data;
  if (!data) return null;
  const items: [string, ArtOut | null | undefined][] = [
    [t("setupKit.logo"), data.chosen_logo],
    [t("setupKit.banner"), data.chosen_banner],
    [t("channelArt.watermark"), data.watermark],
  ];
  return (
    <div data-testid="kit-art" className="space-y-2">
      <p className="text-xs font-medium text-muted">{t("channelArt.kitTitle")}</p>
      {items.some(([, a]) => a) ? (
        <ul className="grid gap-3 sm:grid-cols-3">
          {items.map(([label, a]) =>
            a ? (
              <li key={label} className="space-y-1 rounded-lg border border-line p-2 text-xs">
                <img
                  src={a.download_url}
                  alt={`${label} — ${data.channel_name}`}
                  className={a.role === "BANNER" ? "w-full rounded" : "size-20 rounded"}
                />
                <p className="font-medium">
                  {label} · {a.width}×{a.height}
                </p>
                <ArtActions art={a} label={label} />
              </li>
            ) : (
              <li key={label} className="rounded-lg border border-dashed border-line p-2 text-xs text-muted">
                {label}: {t("channelArt.notChosen")}
              </li>
            ),
          )}
        </ul>
      ) : (
        <p className="text-xs text-muted">{t("channelArt.kitNone")}</p>
      )}
      {data.blueprint && (
        <Link
          className="text-xs text-accent underline"
          to={`/strategies/${data.blueprint.strategy_id}#channel-art`}
        >
          {t("channelArt.kitOpen")}
        </Link>
      )}
    </div>
  );
}
