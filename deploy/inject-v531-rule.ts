import { db } from './src/lib/db/index';
import { ruleVersions } from './src/lib/db/schema';
import { DEFAULT_RULE_CONFIG } from './src/lib/rules/engine';

async function run() {
  console.log('Injecting Narrow-Net v5.3.1 — adjusted thresholds...');

  await db.update(ruleVersions).set({ isActive: false });

  // v5.3 was too strict (0.75/0.65 thresholds caused abstain)
  // v5.3.1: lower thresholds slightly but still much tighter than v5.2.1
  const config = {
    ...DEFAULT_RULE_CONFIG,
    scoreThreshold2D: 0.60,   // v5.3: 0.75 (too strict), v5.2.1: 0.55
    scoreThreshold3D: 0.50,   // v5.3: 0.65 (too strict), v5.2.1: 0.35
    maxMainPicks2D: 2,        // v5.2.1: 3
    maxSecondaryPicks2D: 1,   // v5.2.1: 3
    maxDefensivePicks2D: 1,   // v5.2.1: 2
    maxMainPicks3D: 2,        // v5.2.1: 5
    vetoDepth: 20,
    repeatMode: 'soft_repeat_penalty' as const,
    wraparoundEnabled: true,
    truthMode: true,
    trainingWindow: 120,
    consensusEnabled: true,
    engineVersion: 'v5.3.1',
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
      coldZoneWeight: 0.18,
      instabilityWeight: 0.22,
      recentRepeatWeight: 0.22,
      rejectionMarginWeight: 0.08,
    },
    bankrollStrategy: 'strict-balanced' as const,
    losingStreakReductionStep1: 3,
    losingStreakReductionAmount1: 0.5,
    losingStreakReductionStep2: 5,
    losingStreakReductionAmount2: 0.75,
  };

  await db.insert(ruleVersions).values({
    name: 'Narrow-Net v5.3.1 (Balanced Precision)',
    description: '2D: 2+1+1 picks (was 3+3+2), 3D: 2 picks (was 5). Thresholds 0.60/0.50 (was 0.55/0.35). Stronger penalties.',
    configJson: config,
    isActive: true,
  });

  console.log('Done! v5.3.1 active. Changes from v5.2.1:');
  console.log('  - 2D picks: 3+3+2 → 2+1+1 (8→4 per draw)');
  console.log('  - 3D picks: 5 → 2 per draw');
  console.log('  - scoreThreshold2D: 0.55 → 0.60');
  console.log('  - scoreThreshold3D: 0.35 → 0.50');
}

run();
