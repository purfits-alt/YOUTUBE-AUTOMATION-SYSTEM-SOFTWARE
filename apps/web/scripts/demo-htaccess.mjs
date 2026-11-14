// Apache (Hostinger) rules for the demo folder: every app route serves index.html (single-page app).
import { writeFileSync } from "node:fs";

writeFileSync(
  "dist-demo/.htaccess",
  [
    "RewriteEngine On",
    "RewriteBase /demo/",
    "RewriteCond %{REQUEST_FILENAME} !-f",
    "RewriteCond %{REQUEST_FILENAME} !-d",
    "RewriteRule . /demo/index.html [L]",
    "",
  ].join("\n"),
);
