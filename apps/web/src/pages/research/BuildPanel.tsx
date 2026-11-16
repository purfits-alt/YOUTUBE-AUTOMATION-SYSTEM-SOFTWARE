import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router";
import { useToast } from "../../components/Toasts";
import { Button, Card } from "../../components/ui";
import { t } from "../../i18n";
import { api, call, idempotencyKey, type CandidateOut } from "../../lib/api/client";
import { inputCls, problemText } from "../channels/common";
import { LANGUAGES, splitList, type Lang } from "./common";

type Target = "new" | "existing";

/**
 * Build tab (owner request 2026-11-16): the owner names a niche without running discovery. The
 * channel name is the owner's own, or TubeForge suggests names in the blueprint (A07). With an
 * existing channel (e.g. one onboarded outside discovery) the blueprint is attached to it.
 */
export function BuildPanel() {
  const toast = useToast();
  const qc = useQueryClient();
  const [name, setName] = useState("");
  const [summary, setSummary] = useState("");
  const [language, setLanguage] = useState<Lang>("en");
  const [angles, setAngles] = useState("");
  const [target, setTarget] = useState<Target>("new");
  const [suggest, setSuggest] = useState(true);
  const [channelName, setChannelName] = useState("");
  const [channelId, setChannelId] = useState("");
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);
  const [built, setBuilt] = useState<CandidateOut | null>(null);
  const channels = useQuery({
    queryKey: ["channels", "build"],
    queryFn: () => call(() => api.GET("/api/v1/channels", { params: { query: { limit: 200 } } })),
  });
  const list = channels.data?.items ?? [];
  const ready =
    name.trim().length >= 2 &&
    (target === "new" ? suggest || channelName.trim().length > 0 : channelId.length > 0);
  const submit = async () => {
    setBusy(true);
    try {
      const out = await call(() =>
        api.POST("/api/v1/niches/build", {
          headers: { "Idempotency-Key": idempotencyKey() },
          body: {
            name: name.trim(),
            summary: summary.trim(),
            language,
            originality_angles: splitList(angles).slice(0, 5),
            channel_name: target === "new" && !suggest ? channelName.trim() : null,
            channel_id: target === "existing" ? channelId : null,
            owner_notes: notes.trim(),
          },
        }),
      );
      setBuilt(out.candidate);
      toast(t("buildTab.queued"));
      void qc.invalidateQueries({ queryKey: ["niche-reports"] });
      void qc.invalidateQueries({ queryKey: ["strategies"] });
    } catch (e) {
      toast(problemText(e), "danger");
    } finally {
      setBusy(false);
    }
  };
  return (
    <Card title={t("buildTab.title")}>
      <p className="mb-3 text-sm text-muted">{t("buildTab.hint")}</p>
      <div className="grid gap-3 md:grid-cols-2" data-testid="build-form">
        <div>
          <label htmlFor="build-name" className="block text-sm font-medium">
            {t("buildTab.niche")}
          </label>
          <input
            id="build-name"
            className={inputCls}
            value={name}
            placeholder={t("buildTab.nicheHint")}
            onChange={(e) => setName(e.target.value)}
          />
        </div>
        <div>
          <label htmlFor="build-language" className="block text-sm font-medium">
            {t("buildTab.language")}
          </label>
          <select
            id="build-language"
            className={inputCls}
            value={language}
            onChange={(e) => setLanguage(e.target.value as Lang)}
          >
            {LANGUAGES.map((l) => (
              <option key={l} value={l}>
                {t(`researchPage.lang.${l}`)}
              </option>
            ))}
          </select>
        </div>
        <div className="md:col-span-2">
          <label htmlFor="build-summary" className="block text-sm font-medium">
            {t("buildTab.summary")}
          </label>
          <textarea
            id="build-summary"
            rows={2}
            maxLength={600}
            className={inputCls}
            value={summary}
            onChange={(e) => setSummary(e.target.value)}
          />
        </div>
        <div className="md:col-span-2">
          <label htmlFor="build-angles" className="block text-sm font-medium">
            {t("buildTab.angles")}
          </label>
          <input
            id="build-angles"
            className={inputCls}
            value={angles}
            placeholder={t("buildTab.anglesHint")}
            onChange={(e) => setAngles(e.target.value)}
          />
        </div>
        <fieldset className="md:col-span-2">
          <legend className="text-sm font-medium">{t("buildTab.channel")}</legend>
          <div className="mt-1 flex flex-wrap gap-4 text-sm">
            <label className="flex items-center gap-1">
              <input
                type="radio"
                name="build-target"
                checked={target === "new"}
                onChange={() => setTarget("new")}
              />
              {t("buildTab.newChannel")}
            </label>
            <label className="flex items-center gap-1">
              <input
                type="radio"
                name="build-target"
                checked={target === "existing"}
                onChange={() => setTarget("existing")}
              />
              {t("buildTab.existingChannel")}
            </label>
          </div>
        </fieldset>
        {target === "new" ? (
          <div className="space-y-2 md:col-span-2">
            <label className="flex items-center gap-2 text-sm">
              <input
                type="radio"
                name="build-name-mode"
                checked={suggest}
                onChange={() => setSuggest(true)}
              />
              {t("buildTab.suggestNames")}
            </label>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="radio"
                name="build-name-mode"
                checked={!suggest}
                onChange={() => setSuggest(false)}
              />
              {t("buildTab.ownName")}
            </label>
            {!suggest && (
              <div>
                <label htmlFor="build-channel-name" className="block text-sm font-medium">
                  {t("buildTab.channelName")}
                </label>
                <input
                  id="build-channel-name"
                  className={inputCls}
                  maxLength={80}
                  value={channelName}
                  onChange={(e) => setChannelName(e.target.value)}
                />
              </div>
            )}
          </div>
        ) : (
          <div className="md:col-span-2">
            <label htmlFor="build-channel" className="block text-sm font-medium">
              {t("buildTab.pickChannel")}
            </label>
            <select
              id="build-channel"
              className={inputCls}
              value={channelId}
              onChange={(e) => setChannelId(e.target.value)}
            >
              <option value="">{t("buildTab.choose")}</option>
              {list.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
            {list.length === 0 && <p className="mt-1 text-xs text-muted">{t("buildTab.noChannels")}</p>}
            <p className="mt-1 text-xs text-muted">{t("buildTab.existingHint")}</p>
          </div>
        )}
        <div className="md:col-span-2">
          <label htmlFor="build-notes" className="block text-sm font-medium">
            {t("buildTab.notes")}
          </label>
          <textarea
            id="build-notes"
            rows={2}
            maxLength={2000}
            className={inputCls}
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
          />
        </div>
      </div>
      <div className="mt-4 flex flex-wrap items-center gap-3">
        <Button variant="primary" disabled={!ready || busy} onClick={() => void submit()}>
          {t("buildTab.submit")}
        </Button>
        {built && (
          <p className="text-sm" data-testid="build-done">
            {t("buildTab.done", { name: built.name })}{" "}
            <Link className="text-accent underline" to="/strategies">
              {t("buildTab.openBlueprints")}
            </Link>
          </p>
        )}
      </div>
    </Card>
  );
}
