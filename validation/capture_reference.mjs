#!/usr/bin/env node
// Capture the SDK's swapQuote outputs + the raw pool/bin bytes for one snapshot,
// so check_quote.py can diff the Python library against the on-chain reference.
//
//   npm install first (Node 20 LTS), then:
//   RPC_URL="https://mainnet.helius-rpc.com/?api-key=..." \
//   POOL="<lbPair>" [SWAP_FOR_Y=true|false] [AMOUNTS="0.1,1,5,20,50,100,200"] \
//   npx tsx capture_reference.mjs                        -> reference.json
import { Connection, PublicKey } from "@solana/web3.js";
import pkg from "@meteora-ag/dlmm";
const DLMM = pkg.default ?? pkg;
import BN from "bn.js";
import fs from "fs";

const RPC = process.env.RPC_URL, POOL = process.env.POOL;
if (!RPC || !POOL) { console.error("set RPC_URL and POOL"); process.exit(1); }
const SWAP_FOR_Y = (process.env.SWAP_FOR_Y ?? "true") === "true";
const AMOUNTS = (process.env.AMOUNTS ?? "0.1,1,5,20,50,100,200").split(",").map(Number);
const COUNT = Number(process.env.COUNT ?? 8);   // bin arrays to fetch (raise for large swaps)

const conn = new Connection(RPC, "confirmed");
const dlmm = await DLMM.create(conn, new PublicKey(POOL));
await dlmm.refetchStates();
const p = dlmm.lbPair, sp = p.parameters, vp = p.vParameters;
const decX = dlmm.tokenX.mint.decimals, decY = dlmm.tokenY.mint.decimals;
const inDec = SWAP_FOR_Y ? decX : decY;

const lbPairInfo = await conn.getAccountInfo(new PublicKey(POOL));
const binArrays = await dlmm.getBinArrayForSwap(SWAP_FOR_Y, COUNT);
const pubkeys = binArrays.map((b) => b.publicKey);
const infos = await conn.getMultipleAccountsInfo(pubkeys);

const results = [];
for (const ui of AMOUNTS) {
  const inAmount = new BN(BigInt(Math.round(ui * 10 ** inDec)).toString());
  try {
    const q = await dlmm.swapQuote(inAmount, SWAP_FOR_Y, new BN(50_000), binArrays, true);
    results.push({ inAmount: inAmount.toString(), outAmount: q.outAmount.toString() });
  } catch (e) {
    results.push({ inAmount: inAmount.toString(), error: String(e).slice(0, 140) });
  }
}

fs.writeFileSync("reference.json", JSON.stringify({
  pool: POOL, swapForY: SWAP_FOR_Y, decX, decY,
  lbPairB64: lbPairInfo.data.toString("base64"),
  binArraysB64: infos.map((a, i) => ({ pubkey: pubkeys[i].toBase58(), data: a.data.toString("base64") })),
  // SDK-decoded params, for cross-checking the Python decoder
  sdk: {
    activeId: p.activeId, binStep: p.binStep,
    baseFactor: Number(sp.baseFactor), baseFeePowerFactor: Number(sp.baseFeePowerFactor ?? 0),
    variableFeeControl: Number(sp.variableFeeControl), maxVolatilityAccumulator: Number(sp.maxVolatilityAccumulator),
    filterPeriod: Number(sp.filterPeriod), decayPeriod: Number(sp.decayPeriod), reductionFactor: Number(sp.reductionFactor),
    volatilityAccumulator: Number(vp.volatilityAccumulator), volatilityReference: Number(vp.volatilityReference),
    indexReference: Number(vp.indexReference),
    lastUpdateTimestamp: Number(vp.lastUpdateTimestamp?.toString?.() ?? vp.lastUpdateTimestamp),
  },
  clockTs: Date.now() / 1000,
  results,
}, null, 2));
console.log(`wrote reference.json  active=${p.activeId} binStep=${p.binStep}bp volAcc=${Number(vp.volatilityAccumulator)}`);
