import { db } from './src/lib/db/index';
import { ruleVersions } from './src/lib/db/schema';
import { DEFAULT_RULE_CONFIG } from './src/lib/rules/engine';

async function run() {
  console.log('Injecting Narrow-Net v5.3 Rule — fewer picks, higher precision...');

  // Deactivate all existing rules
  await db.update(ruleVersions).set({ isActive: false });

  // Narrow-net strategy: fewer picks with higher confidence
  // 2D has 100 possible outcomes → picking 1-2 gives 1-2% base hit rate
  // Current problem: too many picks (3 main + 3 sec + 2 def = 8 per draw) dilutes precision
  // Fix: pick only 1-2 highest-scored 2D, 1 3D, raise thresholds
  const narrowConfig = {
    ...DEFAULT_RULE_CONFIG,
    scoreThreshold2D: 0.75,   // Was 0.55 — raise to only pick top-scored
    scoreThreshold3D: 0.65,   // Was 0.35 — raise significantly
    maxMainPicks2D: 1,        // Was 3 — pick only the #1 candidate
    maxSecondaryPicks2D: 1,    // Was 3 — one secondary
    maxDefensivePicks2D: 0,    // Was 2 — no defensive (low value)
    maxMainPicks3D: 1,        // Was 5 — pick only the #1 candidate
    vetoDepth: 20,
    repeatMode: 'soft_repeat_penalty' as const,
    wraparoundEnabled: true,
    truthMode: true,
    trainingWindow: 120,
    consensusEnabled: true,
    engineVersion: 'v5.3.0',
    weights2d: {
      freq30: 0.05,
      freq90: 0.30,
      freq180: 0.35,
      tensHotness: 0.06,
      digitHotness: 0.04,
      neighborFreq: 0.02,
      reversalFreq: 0.02,
      gapPatternBoost: 0.03,
      omissionBalance: 0.03,
      sameWeekdayFreq: 0.04,
      recencyScoreBoost: 0.04,
      lastDrawTransformBoost: 0.02,
      globalTransitionBoost: 0.02,
    },
    weights3d: {
      freq30: 0.05,
      freq90: 0.30,
      freq180: 0.35,
      tensHotness: 0.06,
      digitHotness: 0.04,
      neighborFreq: 0.02,
      reversalFreq: 0.02,
      gapPatternBoost: 0.03,
      omissionBalance: 0.03,
      sameWeekdayFreq: 0.04,
      recencyScoreBoost: 0.04,
      lastDrawTransformBoost: 0.05,
    },
    penalties: {
      coldZoneWeight: 0.20,      // Was 0.15 — increase penalty for cold zones
      instabilityWeight: 0.25,   // Was 0.20 — increase
      recentRepeatWeight: 0.25,  // Was 0.20 — increase
      rejectionMarginWeight: 0.10, // Was 0.05 — increase
    },
    bankrollStrategy: 'strict-balanced' as const,
    losingStreakReductionStep1: 3,
    losingStreakReductionAmount1: 0.5,
    losingStreakReductionStep2: 5,
    losingStreakReductionAmount2: 0.75,
  };

  await db.insert(ruleVersions).values({
    name: 'Narrow-Net v5.3 (Precision Focus)',
    description: 'Fewer picks (1-2 2D, 1 3D), higher thresholds, stronger penalties. Target: 2D 3-5% hit rate, 3D 0.5-1% hit rate.',
    configJson: narrowConfig,
    isActive: true,
  });

  console.log('Done! New rule active. Next prediction cycle will use Narrow-Net v5.3.');
  console.log('Key changes:');
  console.log('  - 2D: 3+3+2 → 1+1+0 picks (8→2 per draw)');
  console.log('  - 3D: 5 → 1 pick per draw');
  console.log('  - scoreThreshold2D: 0.55 → 0.75');
  console.log('  - scoreThreshold3D: 0.35 → 0.65');
  console.log('  - Penalties increased: cold 0.15→0.20, instability 0.20→0.25, repeat 0.20→0.25');
}

run();
