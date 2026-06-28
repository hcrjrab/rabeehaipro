/** @type {import('postcss-load-config').Config} */
// Tailwind CSS v4 uses a dedicated PostCSS plugin. Autoprefixer is built in,
// so it no longer needs a separate entry (unlike v3).
const config = {
  plugins: {
    "@tailwindcss/postcss": {},
  },
};

export default config;
