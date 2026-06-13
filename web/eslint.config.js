import js from "@eslint/js";
import globals from "globals";

export default [
  js.configs.recommended,
  {
    files: ["static/**/*.js"],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: "script",
      globals: { ...globals.browser },
    },
    rules: {
      "prefer-const": "error",
      "no-var": "error",
      eqeqeq: ["error", "smart"],
      "no-unused-vars": ["error", { argsIgnorePattern: "^_" }],
    },
  },
];
