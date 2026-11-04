/**
 * Domain Catalog Barrel — Re-exports focused DDD domain catalog modules:
 * - `section-metadata.ts`: Clinical section metadata, icons, poles, and extraction prompts
 * - `agent-catalog.ts`: Specialist AI agent presentation and quick prompts
 * - `field-schema.ts`: Field input descriptors and dynamic Pydantic v2 JSON Schema parser
 * - `section-coercion.ts`: Strict form payload coercion and validation before API persistence
 */

export * from "./agent-catalog.js";
export * from "./field-schema.js";
export * from "./section-coercion.js";
export * from "./section-metadata.js";
