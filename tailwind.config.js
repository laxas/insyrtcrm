/**
 * Tailwind CSS configuration for InsyrtCRM.
 *
 * Built with the standalone Tailwind CLI (no Node toolchain required) via
 * `make css`. The generated, purged stylesheet is committed at
 * `assets/css/app.css` and served by Django's staticfiles app.
 *
 * `content` lists every place Tailwind utility classes may appear so the
 * JIT engine can tree-shake the output down to only the classes in use.
 */
module.exports = {
  content: [
    "./templates/**/*.html",
    "./apps/**/templates/**/*.html",
    "./apps/**/*.py",
  ],
  theme: {
    extend: {},
  },
  plugins: [],
};
