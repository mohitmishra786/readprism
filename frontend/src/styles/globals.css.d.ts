// Ambient declaration for CSS side-effect imports (e.g. `import "../styles/globals.css"`).
// Required under TypeScript 6 strictness (TS2882) — without it the compiler
// cannot find a module/type declaration for "*.css" imports.
declare module "*.css";
