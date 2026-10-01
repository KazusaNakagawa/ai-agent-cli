// Classify household-ledger descriptions with typesafe-ai/jev.
// Reads money-job.json, writes money-result.json.
//
// All descriptions go into one request as separate choice questions over one
// shared state, so the run costs a single call and does not hit the upstream
// capacity limit that paced compare.mjs to one success every ~5 minutes.
//
// Usage: node money.mjs
import { experimental_evaluate as evaluate } from 'ai';
import { readFileSync, writeFileSync } from 'node:fs';

const dir = new URL('.', import.meta.url).pathname;
const items = JSON.parse(readFileSync(dir + 'money-job.json', 'utf-8'));

// The categories money_rules.json uses, plus an escape hatch for rows that
// belong to a category the rules do not have yet.
const criteria = {
  income_salary: '勤務先からの給与の入金',
  income_bonus: '勤務先からの賞与の入金',
  income_interest: '預金の利息の入金',
  cash_deposit: 'ATM などでの現金の入金',
  insurance: '保険料の引き落とし',
  card_payment: 'クレジットカード利用代金の引き落とし',
  wallet_charge: '決済アプリ・電子マネーへのチャージ',
  housing: '家賃など住居費の支払い',
  other: '上のどれにも当たらない',
};

const state = {
  description: '日本の銀行口座の入出金明細。各行を家計簿のカテゴリに分類する。',
  transactions: items.map((it, i) => ({ no: i, desc: it.desc, direction: it.direction, amount_jpy: it.amount })),
};
const questions = Object.fromEntries(
  items.map((it, i) => [
    `t${i}`,
    { type: 'choice', instructions: `明細 no=${i}（${it.desc}）のカテゴリを選んでください。`, criteria },
  ]),
);

const started = Date.now();
let r;
try {
  r = await evaluate({ model: 'typesafe-ai/jev', state, questions, maxRetries: 5 });
} catch (e) {
  // The SDK error carries the full request body; print only what identifies the failure.
  console.error(`${e?.name ?? 'Error'} (${e?.statusCode ?? '-'}): ${e?.message?.split('\n')[0] ?? e}`);
  process.exit(1);
}
const latency = Date.now() - started;

const results = items.map((it, i) => {
  const a = r.answers[`t${i}`];
  const top = Math.max(...Object.values(a.probabilities));
  return { ...it, jev: a.choice, p: Number(top.toFixed(2)), probabilities: a.probabilities };
});
writeFileSync(dir + 'money-result.json', JSON.stringify({ latency_ms: latency, usage: r.usage, results }, null, 2));

const labeled = results.filter((x) => x.expected);
const agree = labeled.filter((x) => x.jev === x.expected);
console.log(`latency    : ${latency} ms, usage ${JSON.stringify(r.usage)}`);
console.log(`agreement  : ${agree.length}/${labeled.length} (rule-labeled)`);
for (const x of results) {
  const mark = x.expected ? (x.jev === x.expected ? 'OK ' : 'NG ') : '?? ';
  console.log(`${mark} ${x.jev.padEnd(16)} p=${x.p.toFixed(2)}  expected=${x.expected ?? '-'}  ${x.direction} ${x.amount}  ${x.desc}`);
}
