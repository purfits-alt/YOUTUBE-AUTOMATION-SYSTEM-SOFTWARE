import { Link } from "react-router";
import { t } from "../i18n";

export function NotFound() {
  return (
    <div className="space-y-2" data-testid="page-not-found">
      <h1 className="text-2xl font-bold">{t("notFound.title")}</h1>
      <p>{t("notFound.body")}</p>
      <Link to="/" className="text-accent underline">
        {t("notFound.home")}
      </Link>
    </div>
  );
}
