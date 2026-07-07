/** @type {import('postcss-load-config').Config} */
// Tailwind v4: use the official PostCSS plugin. v4 handles vendor prefixing
// internally, so the standalone autoprefixer is no longer needed.
const config = {
  plugins: {
    "@tailwindcss/postcss": {},
  },
};

export default config;
