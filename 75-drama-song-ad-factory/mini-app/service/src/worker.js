// The deployed Worker exposes only its handler. index.js also exports helpers
// and SERVICE_VERSION for tests, which are not valid Worker entrypoints.
export { default } from './index.js';
