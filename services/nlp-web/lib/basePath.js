/**
 * The app is served under a base path when it is reached through the
 * Q-PRIME gateway (http://localhost:8080/assistant/) and at the root when
 * port 3000 is used directly. `next/link` handles the base path itself;
 * plain asset URLs and `fetch()` calls have to be prefixed explicitly.
 */
export const BASE_PATH = process.env.NEXT_PUBLIC_BASE_PATH || "";

export const withBasePath = (path) => `${BASE_PATH}${path}`;
