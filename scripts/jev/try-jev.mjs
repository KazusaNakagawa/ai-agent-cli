// One-shot smoke test for typesafe-ai/jev through Vercel AI Gateway.
// Requires AI_GATEWAY_API_KEY in the environment. Run: node try-jev.mjs
// Writes results/try-jev-<timestamp>.json.
import { experimental_evaluate as evaluate } from 'ai';
import { saveResult } from './results.mjs';

if (!process.env.AI_GATEWAY_API_KEY) {
  console.error('AI_GATEWAY_API_KEY is not set in this shell.');
  process.exit(1);
}

// A news item of the kind the briefing agent filters, used as shared state.
const state = {
  title: 'Palantir raises full-year guidance on accelerating US commercial bookings',
  source: 'Reuters',
  published: '2026-09-29',
  body: 'The company lifted its revenue outlook after US commercial bookings grew faster than expected. Management said remaining performance obligations rose sharply, while GAAP revenue growth was more modest.',
};

const started = Date.now();

const result = await evaluate({
  model: 'typesafe-ai/jev',
  state,
  questions: {
    // boolean -> P(true)
    marketMoving: {
      type: 'boolean',
      instructions: 'Is this item likely to move the stock price on the next trading day?',
    },
    // choice -> one option + distribution
    category: {
      type: 'choice',
      instructions: 'Classify the primary subject of this item.',
      criteria: {
        earnings: 'Financial results, guidance, or bookings',
        product: 'Product or technology announcement',
        regulatory: 'Regulation, legal action, or government policy',
        macro: 'Broad market or economic conditions',
      },
    },
    // score -> fractional position across ordered levels
    confidence: {
      type: 'score',
      instructions: 'How well does the item separate confirmed figures from forward-looking indicators?',
      criteria: [
        'Conflates them entirely',
        'Mentions both but does not distinguish them',
        'Clearly separates confirmed revenue from bookings and RPO',
      ],
    },
  },
});

const elapsed = Date.now() - started;

console.log(JSON.stringify(result.answers, null, 2));
console.log(`\nlatency: ${elapsed}ms`);
console.log('usage:', JSON.stringify(result.usage));
if (result.warnings?.length) console.log('warnings:', JSON.stringify(result.warnings));
saveResult('try-jev', { latency_ms: elapsed, answers: result.answers, usage: result.usage, warnings: result.warnings ?? [] });
