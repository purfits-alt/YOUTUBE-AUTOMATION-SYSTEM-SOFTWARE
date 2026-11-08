import { t } from "../i18n";
import type { Schemas } from "../lib/api/client";
import { Badge } from "./ui";

/** Shared header for project pages 11–18: title, channel, format, state stepper, blocking guards. */
export function ProjectHeader({ project }: { project: Schemas["ProjectSummary"] }) {
  const currentIndex = project.states.indexOf(project.state);
  return (
    <section
      aria-label={t("project.header")}
      data-testid="project-header"
      className="tf-card tf-rise rounded-xl border border-line bg-surface p-5"
    >
      <p className="text-lg font-semibold" dir="auto">
        {project.title}
      </p>
      <p className="mt-0.5 text-sm text-muted">
        {t("project.channel")}: {project.channel} · {t("project.format")}: {project.format}
      </p>
      <ol aria-label={t("project.stepper")} className="mt-3 flex flex-wrap gap-1.5 text-xs">
        {project.states.map((s, i) => (
          <li
            key={s}
            aria-current={i === currentIndex ? "step" : undefined}
            className={`rounded-full border px-2 py-0.5 ${
              i === currentIndex
                ? "border-accent bg-accent font-semibold text-accent-fg"
                : i < currentIndex
                  ? "border-line bg-surface-2"
                  : "border-line text-muted"
            }`}
          >
            {i < currentIndex && <span aria-hidden="true">✓ </span>}
            {s}
          </li>
        ))}
      </ol>
      <div className="mt-3">
        <p className="text-sm font-medium">{t("project.guards")}</p>
        {project.guards.length === 0 ? (
          <p className="text-sm text-muted">{t("project.noGuards")}</p>
        ) : (
          <ul className="mt-1 flex flex-wrap gap-2">
            {project.guards.map((g) => (
              <li key={g}>
                <Badge tone="warn">{g}</Badge>
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}
