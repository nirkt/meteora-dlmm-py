#!/usr/bin/env node
// Live forward-test capture: snapshot bin + pool state, watch real swaps, and for
// each clean single-swap window emit the pre-swap snapshot + the executed amounts
// for live_check.py to score. This validates the library against reality (not the SDK).
//
//   RPC_URL="..." POOL="<lbPair>" [DURATION=3600] [INTERVAL=20] npx tsx live_capture.mjs
//   -> live_events.jsonl
//
// Note: v0-tx account-key resolution for the reserve-vault delta is the one spot to
// eyeball on your first events; the single-swap-window filter keeps the snapshot valid.
import { Connection, PublicKey } from "@solana/web3.js";
import pkg from "@meteora-ag/dlmm";
const DLMM = pkg.default ?? pkg;
import fs from "fs";

const RPC = process.env.RPC_URL, POOL = process.env.POOL;
const DURATION = Number(process.env.DURATION ?? 3600);
const INTERVAL = Number(process.env.INTERVAL ?? 20);
if (!RPC || !POOL) { console.error("set RPC_URL and POOL"); process.exit(1); }

const conn = new Connection(RPC, "confirmed");
const dlmm = await DLMM.create(conn, new PublicKey(POOL));
const decX = dlmm.tokenX.mint.decimals, decY = dlmm.tokenY.mint.decimals;
const reserveX = dlmm.lbPair.reserveX.toBase58(), reserveY = dlmm.lbPair.reserveY.toBase58();
const out = fs.createWriteStream("live_events.jsonl", { flags: "a" });

async function snapshot() {
  await dlmm.refetchStates();
  const both = [...await dlmm.getBinArrayForSwap(true, 8), ...await dlmm.getBinArrayForSwap(false, 8)];
  const pubkeys = [...new Map(both.map((a) => [a.publicKey.toBase58(), a.publicKey])).values()];
  const [infos, lb] = await Promise.all([
    conn.getMultipleAccountsInfo(pubkeys),
    conn.getAccountInfo(new PublicKey(POOL)),
  ]);
  return {
    slot: await conn.getSlot("confirmed"),
    lbPairB64: lb.data.toString("base64"),
    binArraysB64: infos.map((a, i) => ({ pubkey: pubkeys[i].toBase58(), data: a.data.toString("base64") })),
  };
}

function allKeys(tx) {
  const m = tx.transaction.message;
  return [
    ...(m.staticAccountKeys ?? m.accountKeys ?? []).map((k) => k.toString()),
    ...(tx.meta.loadedAddresses?.writable ?? []).map((k) => k.toString()),
    ...(tx.meta.loadedAddresses?.readonly ?? []).map((k) => k.toString()),
  ];
}

function swapFromTx(tx) {
  if (!tx?.meta) return null;
  const keys = allKeys(tx), pre = tx.meta.preTokenBalances ?? [], post = tx.meta.postTokenBalances ?? [];
  const delta = (reserve) => {
    const idx = keys.indexOf(reserve);
    if (idx < 0) return null;
    const a = pre.find((b) => b.accountIndex === idx), b = post.find((b) => b.accountIndex === idx);
    return a && b ? BigInt(b.uiTokenAmount.amount) - BigInt(a.uiTokenAmount.amount) : null;
  };
  const dX = delta(reserveX), dY = delta(reserveY);
  if (dX == null || dY == null) return null;
  if ((dX > 0n && dY > 0n) || (dX < 0n && dY < 0n)) return { liquidity: true };
  if (dX === 0n || dY === 0n) return null;
  const swapForY = dX > 0n;
  return { swapForY, amountIn: (swapForY ? dX : dY).toString(), amountOut: (swapForY ? -dY : -dX).toString() };
}

let prev = await snapshot(), lastSig = null;
const t0 = Date.now();
console.log(`live: pool=${POOL} ${DURATION}s, snapshot/${INTERVAL}s`);
while ((Date.now() - t0) / 1000 < DURATION) {
  await new Promise((r) => setTimeout(r, INTERVAL * 1000));
  const sigs = await conn.getSignaturesForAddress(new PublicKey(POOL), { until: lastSig ?? undefined, limit: 100 });
  if (sigs.length) lastSig = sigs[0].signature;
  const next = await snapshot();
  const win = sigs.filter((s) => s.slot > prev.slot && s.slot <= next.slot && !s.err).reverse();
  const parsed = [];
  for (const s of win) {
    const ev = swapFromTx(await conn.getTransaction(s.signature, { maxSupportedTransactionVersion: 0 }));
    if (ev) parsed.push({ slot: s.slot, ...ev });
  }
  const swaps = parsed.filter((e) => !e.liquidity), liq = parsed.filter((e) => e.liquidity);
  if (swaps.length === 1 && liq.length === 0) {
    out.write(JSON.stringify({ ...swaps[0], decX, decY,
      lbPairB64: prev.lbPairB64, preBinArraysB64: prev.binArraysB64 }) + "\n");
    console.log(`+ ${swaps[0].swapForY ? "X->Y" : "Y->X"} in=${swaps[0].amountIn} out=${swaps[0].amountOut}`);
  } else if (parsed.length) {
    console.log(`- skip window (${swaps.length} swaps, ${liq.length} liq)`);
  }
  prev = next;
}
out.end();
console.log("done -> live_events.jsonl");
