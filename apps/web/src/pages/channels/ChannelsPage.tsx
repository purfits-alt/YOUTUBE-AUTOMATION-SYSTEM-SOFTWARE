import { zodResolver } from "@hookform/resolvers/zod";
import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { Link, useNavigate } from "react-router";
import { z } from "zod";
import { Dialog } from "../../components/Dialog";
import { ProblemDisplay } from "../../components/ProblemDisplay";
import { StatTile } from "../../components/StatTile";
import { StateCard } from "../../components/StateCard";
import { useToast } from "../../components/Toasts";
import { Badge, Button } from "../../components/ui";
import { t } from "../../i18n";
import { api, call, idempotencyKey, type ChannelOut } from "../../lib/api/client";
import { useSelectedChannel } from "../../lib/channel";
import { useChannels } from "../../lib/useBackend";
import { asProblem, LoadingSkeleton, PageTitle } from "../PageView";
import { getPage } from "../registry";
import { inputCls, problemText, StateBadge, TokenBadge } from "./common";

const LANGUAGES = ["en", "es", "fr", "de", "ur"] as const;
const schema = z.object({
  name: z.string().trim().min(1, "Enter a name").max(80),
  content_language: z.enum(LANGUAGES),
  is_test_channel: z.boolean(),
});
type Form = z.infer<typeof schema>;

function AddChannelDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const qc = useQueryClient();
  const toast = useToast();
  const navigate = useNavigate();
  const { setChannelId } = useSelectedChannel();
  const [error, setError] = useState<string | null>(null);
  const { register, handleSubmit, formState } = useForm<Form>({
    resolver: zodResolver(schema),
    defaultValues: { name: "", content_language: "en", is_test_channel: true },
  });
  const submit = handleSubmit(async (values) => {
    setError(null);
    try {
      const created = await call(() =>
        api.POST("/api/v1/channels", {
          body: { ...values, is_monetised: !values.is_test_channel },
          headers: { "Idempotency-Key": idempotencyKey() },
        }),
      );
      await qc.invalidateQueries({ queryKey: ["channels"] });
      setChannelId(created.id);
      toast(t("channelsPage.created", { name: created.name }));
      onClose();
      void navigate(`/channels/${created.id}/onboarding`);
    } catch (e) {
      setError(problemText(e));
    }
  });
  return (
    <Dialog open={open} title={t("channelsPage.addTitle")} onClose={onClose} testId="add-channel-dialog">
      <form onSubmit={(e) => void submit(e)} noValidate className="space-y-4">
        <div>
          <label htmlFor="ch-name" className="block text-sm font-medium">
            {t("channelsPage.name")}
          </label>
          <input id="ch-name" className={inputCls} autoComplete="off" {...register("name")} />
          {formState.errors.name && (
            <p role="alert" className="mt-1 text-sm text-danger-text">
              {formState.errors.name.message}
            </p>
          )}
        </div>
        <div>
          <label htmlFor="ch-lang" className="block text-sm font-medium">
            {t("channelsPage.language")}
          </label>
          <select id="ch-lang" className={inputCls} {...register("content_language")}>
            {LANGUAGES.map((l) => (
              <option key={l} value={l}>
                {t(`languages.${l}`)}
              </option>
            ))}
          </select>
        </div>
        <label className="flex items-start gap-2 text-sm">
          <input type="checkbox" className="mt-1" {...register("is_test_channel")} />
          <span>
            <span className="font-medium">{t("channelsPage.testChannel")}</span>
            <span className="block text-muted">{t("channelsPage.testChannelHint")}</span>
          </span>
        </label>
        {error && (
          <p role="alert" className="rounded-lg bg-danger-soft px-3 py-2 text-sm text-danger-text">
            {error}
          </p>
        )}
        <div className="flex justify-end gap-2">
          <Button onClick={onClose}>{t("confirm.cancel")}</Button>
          <Button type="submit" variant="primary" disabled={formState.isSubmitting}>
            {t("channelsPage.create")}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}

function ChannelCard({ channel }: { channel: ChannelOut }) {
  const qc = useQueryClient();
  const toast = useToast();
  const { setChannelId } = useSelectedChannel();
  const [busy, setBusy] = useState(false);
  const run = async (cmd: "pause" | "resume") => {
    setBusy(true);
    try {
      await call(() =>
        api.POST("/api/v1/channels/{channel_id}/commands/{cmd}", {
          params: { path: { channel_id: channel.id, cmd } },
          headers: { "Idempotency-Key": idempotencyKey() },
        }),
      );
      await qc.invalidateQueries({ queryKey: ["channels"] });
      toast(t(cmd === "pause" ? "channelsPage.paused" : "channelsPage.resumed", { name: channel.name }));
    } catch (e) {
      toast(problemText(e), "danger");
    } finally {
      setBusy(false);
    }
  };
  const canPause = channel.state === "ACTIVE" || channel.state === "CONNECTED";
  return (
    <li
      data-testid="channel-card"
      className="tf-card tf-rise flex flex-col gap-3 rounded-xl border border-line bg-surface p-5"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="truncate text-base font-semibold" dir="auto">
            {channel.name}
          </h2>
          <p className="text-xs text-muted">
            {channel.youtube_handle ?? t("channelsPage.notLinked")} ·{" "}
            {t(`languages.${channel.content_language}`)}
          </p>
        </div>
        <StateBadge state={channel.state} />
      </div>
      <div className="flex flex-wrap gap-1.5">
        <Badge tone="info">{t(`modes.${channel.operating_mode}`)}</Badge>
        {channel.private_only_mode && <Badge tone="ok">{t("badges.privateOnly")}</Badge>}
        {channel.is_test_channel && <Badge tone="neutral">{t("channelsPage.testBadge")}</Badge>}
        <TokenBadge channel={channel} />
      </div>
      <p className="text-sm text-muted">
        {t("channelsPage.testUploads", { count: channel.successful_private_test_uploads })}
      </p>
      <div className="mt-auto flex flex-wrap gap-2">
        <Link
          to={`/channels/${channel.id}/onboarding`}
          onClick={() => setChannelId(channel.id)}
          className="inline-flex min-h-9 items-center rounded-lg bg-accent px-3.5 py-1.5 text-sm font-medium text-accent-fg"
        >
          {channel.state === "ACTIVE" ? t("channelsPage.openSetup") : t("channelsPage.continueSetup")}
        </Link>
        {canPause && (
          <Button disabled={busy} onClick={() => void run("pause")}>
            {t("channelsPage.pause")}
          </Button>
        )}
        {channel.state === "PAUSED" && (
          <Button disabled={busy} onClick={() => void run("resume")}>
            {t("channelsPage.resume")}
          </Button>
        )}
      </div>
    </li>
  );
}

/** Page 3 — Channel Manager (real API since Phase 4). */
export function ChannelsPage() {
  const page = getPage("channels");
  const channels = useChannels();
  const [adding, setAdding] = useState(false);
  const items = channels.data?.items ?? [];
  const connected = items.filter((c) => c.state === "CONNECTED" || c.state === "ACTIVE").length;
  const attention = items.filter((c) => c.state === "NEEDS_REAUTH" || c.oauth_expiring_soon).length;
  const uploads = items.reduce((n, c) => n + c.successful_private_test_uploads, 0);
  return (
    <div className="space-y-4" data-testid="page-channels">
      <PageTitle page={page}>
        <Button variant="primary" onClick={() => setAdding(true)}>
          {t("actions.addChannel")}
        </Button>
      </PageTitle>
      {channels.isPending && <LoadingSkeleton />}
      {channels.isError && (
        <ProblemDisplay problem={asProblem(channels.error)} onRetry={() => void channels.refetch()} />
      )}
      {channels.data && items.length === 0 && (
        <StateCard
          message={t("pages.channels.empty")}
          actionLabel={t("pages.channels.emptyAction")}
          onAction={() => setAdding(true)}
        />
      )}
      {items.length > 0 && (
        <div data-testid="state-success" className="space-y-4">
          <div
            className="tf-stagger grid grid-cols-2 gap-3 lg:grid-cols-4"
            role="group"
            aria-label={t("states.summary")}
          >
            <StatTile label={t("channelsPage.statChannels")} value={String(items.length)} icon="channels" />
            <StatTile label={t("channelsPage.statConnected")} value={String(connected)} icon="check" />
            <StatTile label={t("channelsPage.statAttention")} value={String(attention)} icon="alert" />
            <StatTile label={t("channelsPage.statUploads")} value={String(uploads)} icon="publish" />
          </div>
          <ul className="grid gap-4 md:grid-cols-2 xl:grid-cols-3" aria-label={t("pages.channels.title")}>
            {items.map((c) => (
              <ChannelCard key={c.id} channel={c} />
            ))}
          </ul>
        </div>
      )}
      {adding && <AddChannelDialog open={adding} onClose={() => setAdding(false)} />}
    </div>
  );
}
