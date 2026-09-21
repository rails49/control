// The app is one component. Shoelace's own controls draw with icons from its
// system library, which is compiled in, so nothing is fetched at runtime and
// no asset path has to be set.
//
// Both Shoelace themes are linked where the controls are, and which one the
// page wears is the operating system's answer (ui/theme.ts). It is set here
// rather than in a component: there is one page, and this is it.

import "./ui/tc-app.js";
import { followTheSystem } from "./ui/theme.js";

followTheSystem();
