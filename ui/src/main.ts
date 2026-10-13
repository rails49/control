// The app is one component, and its chrome is `@rails49/look`'s. Shoelace's
// assets are served from the app's own origin (`vite.config.ts`), and
// `look.css` carries Shoelace's light and dark themes, the operating system
// deciding between them.

import "@rails49/look/look.css";
import { setBasePath } from "@shoelace-style/shoelace/dist/utilities/base-path.js";

import "./ui/tc-app.js";

setBasePath("/shoelace");
