// Compare typesafe-ai/jev against the current eval-judge baseline (run_claude).
// Reads job.json, asks Jev the same verdict question, writes compare-result.json.
//
// Jev's upstream rejects bursts with a 429 ("No access to this model at this
// time"), so calls are paced and retried well beyond the SDK default.
//
// Usage: node compare.mjs [limit] [delaySeconds]
import { experimental_evaluate as evaluate } from 'ai';
import { readFileSync, writeFileSync } from 'node:fs';

const dir = new URL('.', import.meta.url).pathname;
const limit = Number(process.argv[2] ?? 20);
const delayMs = Number(process.argv[3] ?? 20) * 1000;
const claims = JSON.parse(readFileSync(dir + 'job.json', 'utf-8')).slice(0, limit);

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// Mirrors prompts/eval_judge.md, expressed as one typed choice question.
const criteria = {
  hit: '元の見立ての方向性が当たった',
  miss: '元の見立ての方向性が外れた',
  partial: '部分的に当たった',
  unresolved: '後日ブリーフィングだけでは判断材料が不足している',
};

const results = [];
for (const [i, c] of claims.entries()) {
  if (i > 0) await sleep(delayMs);
  const state = {
    theme: c.theme,
    direction: c.direction,
    targets: c.targets,
    horizon_days: c.horizon_days,
    type: c.type,
    followup_briefings: c.followups,
  };
  const started = Date.now();
  try {
    const r = await evaluate({
      model: 'typesafe-ai/jev',
      state,
      maxRetries: 5,
      questions: {
        verdict: {
          type: 'choice',
          instructions:
            '投資ブリーフィングの見立てを、後日ブリーフィング（真値）と突き合わせて判定してください。',
          criteria,
        },
      },
    });
    results.push({
      id: c.id,
      baseline: c.baseline_verdict,
      baseline_confidence: c.baseline_confidence,
      jev: r.answers.verdict.choice,
      probabilities: r.answers.verdict.probabilities,
      latency_ms: Date.now() - started,
      usage: r.usage,
      full_chars: c.followups_full_chars,
      truncated: c.truncated,
    });
    process.stdout.write('o');
  } catch (e) {
    results.push({
      id: c.id,
      baseline: c.baseline_verdict,
      error: e?.message?.slice(0, 200) ?? String(e),
      latency_ms: Date.now() - started,
      full_chars: c.followups_full_chars,
    });
    process.stdout.write('x');
  }
}
process.stdout.write('\n');

writeFileSync(dir + 'compare-result.json', JSON.stringify(results, null, 2));

const ok = results.filter((r) => !r.error);
const agree = ok.filter((r) => r.jev === r.baseline);
const lat = ok.map((r) => r.latency_ms).sort((a, b) => a - b);
const inTok = ok.reduce((s, r) => s + (r.usage?.inputTokens ?? 0), 0);

console.log(`calls      : ${results.length} (ok ${ok.length}, error ${results.length - ok.length})`);
if (ok.length) {
  console.log(`agreement  : ${agree.length}/${ok.length}`);
  console.log(`latency ms : min ${lat[0]} / median ${lat[Math.floor(lat.length / 2)]} / max ${lat.at(-1)}`);
  console.log(`input tok  : total ${inTok}, cost $${((inTok / 1e6) * 0.042).toFixed(6)}`);
}
const firstError = results.find((r) => r.error);
if (firstError) console.log(`first error: ${firstError.error}`);
