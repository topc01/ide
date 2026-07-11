import "@testing-library/jest-dom";

// jsdom lacks these; Radix (Select/Dialog) needs them for pointer-based interactions.
// Guarded because some test files opt into `@vitest-environment node`, where `Element` doesn't exist.
if (typeof Element !== "undefined") {
  if (!Element.prototype.hasPointerCapture) Element.prototype.hasPointerCapture = () => false;
  if (!Element.prototype.releasePointerCapture) Element.prototype.releasePointerCapture = () => {};
  if (!Element.prototype.scrollIntoView) Element.prototype.scrollIntoView = () => {};
}
