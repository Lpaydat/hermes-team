#!/usr/bin/env node
/**
 * Microbenchmark template for comparing two JS/TS libraries.
 *
 * Usage: node --expose-gc benchmark-template.mjs
 *
 * Copy this file, adapt the buildA/buildB functions to your libraries,
 * and run. Measures: query/build overhead, memory per operation.
 *
 * Prerequisites:
 *   npm install <lib-a> <lib-b>
 *   node --expose-gc benchmark-template.mjs
 *
 * The --expose-gc flag is REQUIRED for accurate memory measurement.
 */

// ============================================================
// IMPORTS — adapt these to your libraries
// ============================================================

// Example: Drizzle vs Kysely query builders
// Uncomment and adapt:

// import { pgTable, serial, varchar, integer } from 'drizzle-orm/pg-core';
// import { eq, and, or, gt, desc, sql as dsql } from 'drizzle-orm';
// import { PgDialect } from 'drizzle-orm/pg-core/dialect';
// import { drizzle } from 'drizzle-orm/pg-proxy';
//
// import { Kysely } from 'kysely';
// import { DefaultQueryCompiler } from 'kysely';

// ============================================================
// MOCK DB SETUP — no real DB connection needed
// ============================================================

// Drizzle: use pg-proxy with a mock callback (NOT node-postgres, which requires `pg`)
//
// const db = drizzle(async (sql, params, method) => {
//   return { rows: [] };
// }, { schema: {}, mode: 'default' });

// Kysely: minimal mock driver
//
// class MockDriver {
//   async init() {}
//   async acquireConnection() { return {}; }
//   async releaseConnection() {}
//   async destroy() {}
// }
// const kysely = new Kysely({
//   dialect: {
//     createDriver: () => new MockDriver(),
//     createAdapter: () => ({}),
//     createQueryCompiler: () => new DefaultQueryCompiler(),
//     createIntrospector: () => ({}),
//   },
// });

// ============================================================
// BUILD FUNCTIONS — one per library, equivalent queries
// ============================================================

function buildA(i) {
  // Library A: build the query and return the compiled result
  // Example (Drizzle):
  // return db.select({ id: users.id }).from(users).where(eq(users.id, i)).toSQL();
  throw new Error('Implement buildA');
}

function buildB(i) {
  // Library B: build the equivalent query
  // Example (Kysely):
  // return kysely.selectFrom('users').select('id').where('id', '=', i).compile();
  throw new Error('Implement buildB');
}

// ============================================================
// BENCHMARK HARNESS — don't modify below this line
// ============================================================

function bench(fn, label, n) {
  // Warmup
  for (let i = 0; i < 3000; i++) fn(i);

  let start = process.hrtime.bigint();
  for (let i = 0; i < n; i++) fn(i);
  let end = process.hrtime.bigint();
  const usPerOp = Number(end - start) / n / 1000;

  console.log(`  ${label}: ${usPerOp.toFixed(2)} µs/op`);
  return usPerOp;
}

function benchMemory(fn, label) {
  if (global.gc) global.gc();
  const before = process.memoryUsage().heapUsed;
  const results = [];
  for (let i = 0; i < 10000; i++) results.push(fn(i));
  const after = process.memoryUsage().heapUsed;
  const bytesPerOp = ((after - before) / 10000).toFixed(0);
  console.log(`  ${label}: ${bytesPerOp} bytes/op retained`);
  results.length = 0;
  return parseInt(bytesPerOp);
}

// --- Verify both produce valid output before benchmarking ---
console.log('=== VERIFICATION ===');
const sampleA = buildA(0);
const sampleB = buildB(0);
console.log('Library A output:', JSON.stringify(sampleA).slice(0, 120));
console.log('Library B output:', JSON.stringify(sampleB).slice(0, 120));
console.log('');

// --- Complex query benchmark ---
console.log('=== COMPLEX QUERY BUILD OVERHEAD ===');
const N_COMPLEX = 100000;
const aComplex = bench(buildA, 'Library A', N_COMPLEX);
const bComplex = bench(buildB, 'Library B', N_COMPLEX);
const ratio = (Math.max(aComplex, bComplex) / Math.min(aComplex, bComplex)).toFixed(2);
const winner = aComplex < bComplex ? 'A' : 'B';
console.log(`  → Library ${winner} is ${ratio}x faster`);
console.log('');

// --- Memory per operation ---
console.log('=== MEMORY PER OPERATION (10k retained) ===');
benchMemory(buildA, 'Library A');
benchMemory(buildB, 'Library B');
