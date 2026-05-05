# Nami Design System

A premium gold-and-dark design system for Nami — AI-powered market intelligence and lottery analytics platform targeting Thai and Southeast Asian audiences.

## 1. Visual Direction

- **Gold-first palette**: Every surface leads with warm gold tones (#D4A843, #F5D77A) against deep dark backgrounds (#0F0F14, #1A1A24) — financial confidence meets premium subscription feel
- **Thai-English bilingual typography**: Prompt loop at 56px, body at 16px, Thai text in Noto Sans Thai, English in Inter — clean, modern, no serif
- **Card-centric layout**: Signal cards, prediction cards, and pricing tables are the primary unit — 8px-12px radius, subtle gold border glow on hover
- **Dark premium aesthetic**: Backgrounds are near-black with warm undertones (#0F0F14), not pure black — feels like a premium trading terminal, not a generic dark mode
- **Gold gradient accents**: Linear gradients from #D4A843 → #F5D77A for CTAs, highlights, and brand moments — never flat gold, always luminous
- **Compact mobile-first**: Telegram audience is mobile-primary — 100vw layouts, stacked cards, no sidebars on mobile

## 2. Color Palette & Roles

### Primary
- **Nami Gold** (`#D4A843`): Primary brand color, CTA backgrounds, signal highlights, premium badges. A warm, confident gold that says "intelligence" not "flashy"
- **Gold Light** (`#F5D77A`): Gradient endpoint, hover states, accent highlights, gold text on dark surfaces
- **Deep Dark** (`#0F0F14`): Page background, card backgrounds in dark mode. Near-black with warm purple undertone
- **Surface Dark** (`#1A1A24`): Card surfaces, elevated panels, secondary backgrounds. Darker than gray, warmer than black

### Accent Colors
- **Signal Green** (`#22C55E`): Bullish signals, positive predictions, "Long" direction indicators
- **Signal Red** (`#EF4444`): Bearish signals, risk warnings, "Short" direction indicators
- **Neutral Gray** (`#94A3B8`): Muted text, secondary information, "No Trade" indicators
- **Premium Purple** (`#8B5CF6`): VIP badges, premium features, lottery special draw indicators

### Interactive
- **Gold Glow** (`rgba(212, 168, 67, 0.15)`): Focus rings, active card borders, subtle brand presence
- **Hover Gold** (`#E5BC5A`): Button hover, link hover — slightly brighter than primary gold
- **Active Dark** (`#252530`): Pressed button background, active tab indicators

## 3. Typography

### Font Stack
- **Primary (English)**: `Inter`, system-ui, sans-serif — clean, geometric, technical
- **Primary (Thai)**: `Noto Sans Thai`, sans-serif — matches Inter's x-height and weight range
- **Monospace**: `JetBrains Mono`, monospace — for prices, numbers, prediction digits

### Scale
- **Display**: 56px/1.1 — Hero headlines ("Nami Premium")
- **H1**: 36px/1.2 — Section titles ("สัญญาณวันนี้")
- **H2**: 24px/1.3 — Card titles ("XAU/USD Signal")
- **Body**: 16px/1.6 — Descriptions, signal reasons
- **Caption**: 13px/1.4 — Timestamps, confidence levels, metadata
- **Mono Display**: 32px — Price values, prediction numbers

### Weight Usage
- 700: Headlines, CTA text, signal direction
- 600: Card titles, section labels
- 400: Body text, descriptions
- 300: Captions, metadata

## 4. Spacing & Layout

- **Base unit**: 4px — all spacing is a multiple of 4
- **Card padding**: 16px mobile, 24px desktop
- **Section gap**: 32px between signal cards, 48px between sections
- **Max content width**: 480px mobile-primary (Telegram audience), 1200px desktop
- **Grid**: 1-column mobile, 2-column tablet, 3-column desktop for signal grids
- **Card aspect**: Signal cards 16:9 minimum, prediction cards square-ish

## 5. Components

### Signal Card
- Gold left border (3px) for active signals
- Direction badge (Long=green, Short=red, No Trade=gray) top-right
- Symbol + price in mono display
- Confidence as progress bar (gold fill)
- Risk level as colored dot (High=red, Medium=yellow, Low=green)
- Disclaimer footer in caption gray

### Prediction Card
- Purple left border for lottery
- Numbers in mono display, spaced evenly
- Region badge (ฮานอย/ลาว) top-left
- Method tag below numbers
- Disclaimer: "AI statistical analysis ไม่ใช่การันตีผล"

### Pricing Table
- 3 tiers: Basic (฿299), Pro (฿599), VIP (฿999)
- Gold-highlighted recommended tier
- Check marks in gold, crosses in gray
- CTA button: gold gradient, white text

### Navigation
- Bottom tab bar on mobile (4 items: สัญญาณ, ล็อตเตอรี่, พอร์ต, โปรไฟล์)
- Top navbar on desktop with gold accent underline on active

## 6. Motion & Animation

- **Signal card entrance**: fade-in + slight upward slide (200ms ease-out)
- **Number reveal**: staggered fade-in for prediction digits (50ms per digit)
- **Gold pulse**: subtle opacity oscillation on active signal borders (2s infinite)
- **Price ticker**: smooth number transition when price updates (300ms ease)
- **Tab switch**: cross-fade (150ms)
- **No**: bounce, scale, rotate, or playful animations — premium = restrained

## 7. Voice & Tone

- **Bilingual**: Thai primary with English technical terms (สัญญาณ Signal, ความมั่นใจ Confidence)
- **Professional but approachable**: Not cold financial jargon, not casual slang
- **Disclaimer-forward**: Every prediction and signal includes risk disclaimer naturally, not as afterthought
- **No guarantees**: Never use words like "การันตี", "แน่นอน", "sure", "guaranteed"
- **Confidence-graded**: Always state confidence level (สูง/ปานกลาง/ต่ำ) alongside predictions
- **Action-oriented**: End messages with clear next step ("ดูรายละเอียด →", "สมัครเลย →")

## 8. Brand Assets

- **Logo**: Nami wordmark in gold on dark, or dark on gold
- **Icon**: Wave/flow symbol representing market flow + AI processing
- **Tagline**: "AI Intelligence · Premium Signals" (English) / "สัญญาณ AI ระดับพรีเมียม" (Thai)
- **Watermark**: Subtle gold wave pattern at 5% opacity on card backgrounds
- **Avatar**: Gold circle with Nami icon, used in Telegram bot profile

## 9. Anti-Patterns

- **No guarantee language**: Never "guaranteed profit", "sure win", "แน่นอน"
- **No generic blue**: No default blue (#3B82F6) — Nami is gold, not blue
- **No playful emojis in signals**: Professional tone means 🔔✅⚠️ only, no 🎉🚀💰
- **No full-white backgrounds**: Always dark or very dark — white is only for text on dark
- **No auto-playing media**: Signals are text-first, media is supplementary
- **No financial advice framing**: "AI statistical analysis" not "investment advice"
- **No English-only for Thai audience**: Always bilingual, Thai first for consumer-facing
- **No pill-shaped buttons**: Use 8px radius, not full-radius pills — premium = structured
