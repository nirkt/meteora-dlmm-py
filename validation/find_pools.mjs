#!/usr/bin/env node
// Lists live SOL-USDC DLMM pools sorted by 24h volume.
// Node 18+ (global fetch).  npx tsx find_pools.mjs
const SOL = "So11111111111111111111111111111111111111112";
const USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v";

const res = await fetch("https://dlmm.datapi.meteora.ag/pools");
if (!res.ok) {
  const errText = await res.text();
  console.error(`API failed: ${res.status} ${res.statusText}`);
  console.error(`Response body: ${errText || "(empty)"}`);
  process.exit(1);
}

let all;
try {
  const body = await res.json();
  if (Array.isArray(body)) {
    all = body;
  } else if (body && typeof body === "object") {
    const arrayKey = Object.keys(body).find((k) => Array.isArray(body[k]));
    if (!arrayKey) {
      console.error("No array found in the API response.");
      process.exit(1);
    }
    all = body[arrayKey];
  }
} catch {
  console.error("Failed to parse the API response as JSON.");
  process.exit(1);
}

const num = (v) => (Number(v ?? 0) || 0);
// Meteora datapi nests tokens under token_x/token_y and config under pool_config.
const isSolUsdc = (p) => {
  const x = p.token_x?.address, y = p.token_y?.address;
  return (x === SOL && y === USDC) || (x === USDC && y === SOL);
};

const pools = all.filter(isSolUsdc)
  .map((p) => ({
    address: p.address,
    step: p.pool_config?.bin_step,
    fee: p.pool_config?.base_fee_pct,
    tvl: num(p.tvl),
    vol: num(p.volume?.["24h"]),
  }))
  .sort((a, b) => b.vol - a.vol);

if (pools.length === 0) {
  console.log("No SOL-USDC pools matched. The API schema may have changed —");
  console.log("uncomment the next line to inspect one raw element and fix the keys above.");
  // console.log(all[0]);
  process.exit(0);
}

console.log("address".padEnd(46), "step", "fee%", "TVL$".padStart(15), "vol24h$".padStart(15));
for (const p of pools.slice(0, 12))
  console.log(p.address.padEnd(46), String(p.step ?? "").padStart(4), String(p.fee ?? "").padStart(4),
              Math.round(p.tvl).toLocaleString().padStart(15),
              Math.round(p.vol).toLocaleString().padStart(15));

console.log("\nTip: pick a small bin step (1-4 bp) with decent TVL. Small swaps then cross");
console.log("     several bins, which is what actually exercises the quote math.");
