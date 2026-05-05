---
od:
  mode: prototype
  surface: web
  platform: mobile
  scenario: marketing
  previewType: html
  designSystemRequired: true
  defaultFor: ["nami signal", "nami landing", "nami premium"]
  featured: true
  fidelity: high
---

# Nami Premium Signal Card Generator

Generate a Nami Premium signal/prediction card for Telegram and web display.

## When to use
When the brief mentions "nami signal card", "nami premium card", "gold signal display", "lottery prediction card", "nami landing", or "nami premium page".

## Rules

1. **Always start with a question form** asking: symbol/region, signal type (gold/lottery/trading), confidence level, and target audience (Thai/English/bilingual)

2. **Use the active design system** for all colors, typography, and spacing tokens

3. **Signal cards must include**:
   - Symbol + price in monospace display
   - Direction badge (Long=green, Short=red, No Trade=gray)
   - Confidence progress bar (gold fill)
   - Risk level indicator
   - Disclaimer: "AI statistical analysis ไม่ใช่การันตีผล"

4. **Prediction cards must include**:
   - Numbers in monospace, evenly spaced
   - Region badge (ฮานอย/ลาว)
   - Method tag
   - Same disclaimer

5. **Pricing tables must include**:
   - 3 tiers: Basic (฿299), Pro (฿599), VIP (฿999)
   - Gold-highlighted recommended tier
   - CTA: "สมัครเลย →"

6. **Mobile-first layout**: 100vw, stacked cards, no sidebars

7. **Bilingual**: Thai primary with English technical terms

8. **No guarantee language**: Never use "การันตี", "แน่นอน", "guaranteed", "sure win"

9. **Dark premium aesthetic**: Near-black backgrounds (#0F0F14), gold accents (#D4A843)

10. **Animations**: Subtle only — fade-in cards (200ms), gold pulse on active signals (2s), no bounce/rotate
