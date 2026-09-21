/**
 * Which Shoelace theme the page wears.
 *
 * Both themes are linked and `prefers-color-scheme` decides; there is no
 * toggle in the page, a person having made that choice once already in the
 * operating system
 * ([LOOK.md](https://github.com/rails49/.github/blob/main/docs/LOOK.md),
 * ADR-0003). The app's own palette follows the same query in CSS
 * (`tc-app.styles.ts`); this is only Shoelace's half of it.
 *
 * Shoelace's dark theme is a class rather than a media query — its sheet is
 * `.sl-theme-dark, :host`, and the sheets are linked at the document, where
 * `:host` matches nothing — so something has to put that class on the document
 * and take it off again. This is that something and the whole of it. Reading
 * the preference is not offering a choice.
 */

/**
 * Wear the theme the system asks for, and keep wearing it: the class goes on
 * now and again whenever the preference changes, which is what makes a page
 * left open follow a machine that turns dark at sunset.
 */
export function followTheSystem(root: HTMLElement = document.documentElement) {
  const dark = window.matchMedia("(prefers-color-scheme: dark)");
  const wear = () => root.classList.toggle("sl-theme-dark", dark.matches);
  dark.addEventListener("change", wear);
  wear();
}
