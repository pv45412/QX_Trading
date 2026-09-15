# UI Design Rule: Zero-Glare Warm & Neutral Themes

## Core Principles

1. **Zero-Glare Warm & Neutral Aesthetic**:
   - Strictly NO glaring neon cyan/blue glow or harsh pure white glare (`#ffffff`).
   - Default to warm, low-strain dark charcoal and warm obsidian backgrounds (`#0f0e0d`, `#171513`).
   - Primary text uses high-legibility warm off-white / ivory (`#e6e1da`, `#f4efe6`).
   - Muted secondary text uses warm sand (`#a39b91`, `#9d938a`).
   - Signal accents use warm amber gold (`#d9a05b`), muted sage green (`#7ca982`), and warm terracotta brick (`#c96a5b`).

2. **User-Selectable Zero-Glare Themes**:
   - **Warm Obsidian** (`data-theme="warm"` / Default): Deep warm charcoal canvas with warm amber and muted sage accents.
   - **Mocha Dark** (`data-theme="mocha"`): Warm coffee and bronze sand theme.
   - **Neutral Slate** (`data-theme="neutral"`): Soft neutral dark gray theme.
   - **Stealth Soft** (`data-theme="stealth"`): Zero-glare soft black theme.

3. **No Cyber / No Blue Glare**:
   - Cyberpunk and high-contrast electric blue glows are eliminated.
   - Interactive components, sidebars, and cards use soft warm borders (`var(--qx-border)`) and smooth transitions without harsh contrast.
