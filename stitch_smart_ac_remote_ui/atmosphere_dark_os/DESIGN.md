---
name: Atmosphere Dark OS
colors:
  surface: '#0e141b'
  surface-dim: '#0e141b'
  surface-bright: '#343a42'
  surface-container-lowest: '#090f16'
  surface-container-low: '#161c23'
  surface-container: '#1a2027'
  surface-container-high: '#252a32'
  surface-container-highest: '#2f353d'
  on-surface: '#dde3ed'
  on-surface-variant: '#bac9cc'
  inverse-surface: '#dde3ed'
  inverse-on-surface: '#2b3139'
  outline: '#849396'
  outline-variant: '#3b494c'
  surface-tint: '#00daf3'
  primary: '#c3f5ff'
  on-primary: '#00363d'
  primary-container: '#00e5ff'
  on-primary-container: '#00626e'
  inverse-primary: '#006875'
  secondary: '#7bd0ff'
  on-secondary: '#00354a'
  secondary-container: '#00a6e0'
  on-secondary-container: '#00374d'
  tertiary: '#a8ffd2'
  on-tertiary: '#003824'
  tertiary-container: '#5be9ad'
  on-tertiary-container: '#006645'
  error: '#ffb4ab'
  on-error: '#690005'
  error-container: '#93000a'
  on-error-container: '#ffdad6'
  primary-fixed: '#9cf0ff'
  primary-fixed-dim: '#00daf3'
  on-primary-fixed: '#001f24'
  on-primary-fixed-variant: '#004f58'
  secondary-fixed: '#c4e7ff'
  secondary-fixed-dim: '#7bd0ff'
  on-secondary-fixed: '#001e2c'
  on-secondary-fixed-variant: '#004c69'
  tertiary-fixed: '#6ffbbe'
  tertiary-fixed-dim: '#4edea3'
  on-tertiary-fixed: '#002113'
  on-tertiary-fixed-variant: '#005236'
  background: '#0e141b'
  on-background: '#dde3ed'
  surface-variant: '#2f353d'
typography:
  display-hero:
    fontFamily: Inter
    fontSize: 72px
    fontWeight: '700'
    lineHeight: 76px
    letterSpacing: -0.04em
  display-hero-mobile:
    fontFamily: Inter
    fontSize: 56px
    fontWeight: '700'
    lineHeight: 60px
    letterSpacing: -0.03em
  headline-lg:
    fontFamily: Inter
    fontSize: 32px
    fontWeight: '600'
    lineHeight: 40px
    letterSpacing: -0.02em
  headline-md:
    fontFamily: Inter
    fontSize: 24px
    fontWeight: '600'
    lineHeight: 32px
    letterSpacing: -0.015em
  headline-sm:
    fontFamily: Inter
    fontSize: 20px
    fontWeight: '600'
    lineHeight: 28px
    letterSpacing: -0.01em
  title-md:
    fontFamily: Inter
    fontSize: 16px
    fontWeight: '600'
    lineHeight: 24px
    letterSpacing: -0.005em
  body-lg:
    fontFamily: Inter
    fontSize: 16px
    fontWeight: '400'
    lineHeight: 24px
    letterSpacing: 0em
  body-md:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 20px
    letterSpacing: 0.01em
  body-sm:
    fontFamily: Inter
    fontSize: 12px
    fontWeight: '400'
    lineHeight: 16px
    letterSpacing: 0.01em
  label-md:
    fontFamily: Inter
    fontSize: 12px
    fontWeight: '600'
    lineHeight: 16px
    letterSpacing: 0.06em
  label-sm:
    fontFamily: Inter
    fontSize: 11px
    fontWeight: '500'
    lineHeight: 14px
    letterSpacing: 0.08em
rounded:
  sm: 0.5rem
  DEFAULT: 1rem
  md: 1.5rem
  lg: 2rem
  xl: 3rem
  full: 9999px
spacing:
  gutter: 0.75rem
  gutter-md: 1rem
  margin: 1.25rem
  margin-md: 1.5rem
  space-xs: 0.25rem
  space-sm: 0.5rem
  space-md: 1rem
  space-lg: 1.5rem
  space-xl: 2rem
---

## Brand & Style

This design system is engineered for next-generation smart thermal and climate control, balancing technical precision with sensorial, premium atmosphere management. Built primarily for native mobile experiences (iOS and Android), it creates an environment of quiet luxury, technological responsiveness, and immediate physical clarity.

### Aesthetic Foundation
- **Dark Neomorphic & Glassmorphic Fusion**: Deep slate and obsidian backgrounds meet frosted tactile elements. Elevated surfaces rely on soft multi-layered ambient glows, translucent backdrops (`backdrop-filter: blur`), and delicate 1px border highlights imitating sub-surface light scattering.
- **Atmospheric Glow & Bioluminescence**: Dynamic feedback relies on vibrant cyan, ice blue, and emerald accents. Active states appear as illuminated gas, cold airflow, or internal diode glows rather than flat ink.
- **Physical Feedback Metaphors**: Controls feel tangible and weighted—sliders feature sunken grooved tracks, while primary toggle actions feature recessed/extruded states with diffused neon backlighting.

## Colors

The palette revolves around deep atmospheric slate layers punctuated by cryogenic neon accents that communicate temperature, airflow speed, and power states.

### Core Canvas & Surfaces
- **Canvas Base**: `#0B1118` (Obsidian Deep)
- **Surface Elevation 1 (Card Base)**: `#111A24` (Subtle Slate)
- **Surface Elevation 2 (Elevated Panels & Modals)**: `#1B2635` (Atmospheric Slate)
- **Surface Glass Overlay**: `rgba(27, 38, 53, 0.65)` with `16px` to `24px` blur

### Brand & Interactive Accents
- **Primary / Active Glow (Cyan Neon)**: `#00E5FF` — Main indicator for active cold flow, temperature sliders, and key power states.
- **Secondary / Ambient Air (Ice Blue)**: `#38BDF8` — Secondary feedback, secondary status badges, and gentle air stream gradients.
- **Tertiary / Eco Efficiency (Emerald Mint)**: `#10B981` — Energy-saving modes, healthy filter states, and active connection monitors.
- **Alert / Warm Mode (Thermal Amber)**: `#F59E0B` — Heating mode, diagnostic warnings, and critical filter notifications.

### Borders & Translucency
- **Glass Border Stroke**: `rgba(255, 255, 255, 0.08)` to `rgba(56, 189, 248, 0.25)` on active items.
- **Inner Rim Lighting**: Inset `rgba(255, 255, 255, 0.12)` along top edges to simulate glass bevels.

## Typography

The typography uses Inter across all viewports to provide a crisp, modern, and legible layout on high-density OLED and LCD displays.

### Text Treatments & Hierarchy
- **Primary Metrics (`display-hero-mobile`, `display-hero`)**: Reserved for primary climate readouts (e.g., current set temperature "24°C"). Uses tight tracking and bold optical weight to command the hierarchy without requiring high-contrast white fills across large surfaces.
- **Section Headers & Uppercase Metadata (`label-md`, `label-sm`)**: Formatted in all-caps with expanded tracking (`0.06em` to `0.08em`) and reduced opacity (`60% - 70%` white) to denote operational modes, connection protocols, and hardware status.
- **Values & Readouts**: Status pairs (e.g., "Modo" / "Auto") use a subdued `body-sm` label stacked above a weighted `title-md` value in pure white (`#FFFFFF`) or active Cyan (`#00E5FF`).

## Layout & Spacing

The layout is built around mobile-first thumb ergonomics, concentrating interactive sliders and tactile mode chips within the lower 60% of the display, while atmospheric airflow graphics and ambient statistics occupy the upper section.

### Layout Model
- **Grid Structure**: 4-column fluid layout on mobile viewports with `12px` gutters and `20px` margins. Expands to an 8-column layout on small tablets and foldable displays.
- **Vertical Flow**:
  1. *Top Bar*: Ambient temperature and remote device status.
  2. *Graphic Hero Zone*: Air conditioner visualization and dynamic airflow particle canvas.
  3. *Metric Zone*: Large centered temperature target.
  4. *Interaction Center*: Recessed temperature slider with stepper increments.
  5. *Action Grid*: 4-column distributed mode cards (Cool, Fan, Sleep, Eco).
  6. *Bottom Anchored Bar*: Connection ping, time sync, and global settings trigger.

## Elevation & Depth

Depth is established through dark-mode neomorphism combined with frosted glass layers rather than plain dropped shadows.

### Atmospheric Depth Tiers
1. **Level 0 (Recessed Background)**: `#0B1118`. Deep, light-absorbent base layer.
2. **Level 1 (Recessed Well / Slider Tracks)**: Inset shadows created with `inset 0 3px 6px rgba(0, 0, 0, 0.6), inset 0 1px 2px rgba(0, 0, 0, 0.8)` with a dark slate background (`#0A0F15`).
3. **Level 2 (Tactile Glass Cards & Buttons)**: Background `rgba(27, 38, 53, 0.55)` with `backdrop-filter: blur(20px)`. Outer drop shadow: `0 8px 24px rgba(0, 0, 0, 0.35)`. Top perimeter highlighted via `border-top: 1px solid rgba(255, 255, 255, 0.12)` and `border-bottom: 1px solid rgba(255, 255, 255, 0.03)`.
4. **Level 3 (Active / Bioluminescent Glow)**: Used when modes or the power button are active. Layered dynamic glow using twin box shadows: `0 0 16px rgba(0, 229, 255, 0.45), 0 0 32px rgba(0, 229, 255, 0.15)`. Border glows with `border: 1px solid rgba(0, 229, 255, 0.75)`.

## Shapes

The design system adopts a soft, pill-forward shape scale (`roundedness: 3`) reflecting modern iOS and Android smart device guidelines. Generous radiuses make dark interactive tiles feel comfortable for repetitive touch gestures.

- **Primary Tiles & Quick Actions**: `rounded-2xl` (1.25rem / 20px) to `rounded-3xl` (1.75rem / 28px).
- **Steppers & Sliders**: Fully rounded capsule contours (`rounded-full` / 9999px) for slider thumbs and +/- adjustment buttons.
- **Power Button**: Perfect circle (`rounded-full`) framed with an outer radial glow ring.

## Components

### Power Button (Primary Tactile Toggle)
- **Inactive**: Elevated circle (`56x56px` to `64x64px`), frosted slate background (`#1B2635`), subtle outer shadow, stroke `rgba(255, 255, 255, 0.1)`.
- **Active**: Inner glow with cyan icon (`#00E5FF`), encased in an exterior halo: `box-shadow: 0 0 24px rgba(0, 229, 255, 0.5)`.

### Mode & Function Cards
- **Structure**: Aspect ratio close to 1:1, vertical stack containing an icon (`24px`), small status label, and bold state value.
- **Idle State**: Semi-translucent dark glass (`rgba(27, 38, 53, 0.4)`), `1px` subtle boundary border (`rgba(255, 255, 255, 0.06)`), icons in muted slate (`#94A3B8`).
- **Selected State**: Cyan or emerald neon contour (`1.5px solid #00E5FF` or `#10B981`), diffused internal gradient (`linear-gradient(180deg, rgba(0, 229, 255, 0.12) 0%, rgba(27, 38, 53, 0.5) 100%)`), and glowing icon.

### Temperature Slider & Steppers
- **Track**: Sunken capsule with deep inset shadow and dynamic neon fill indicating current capacity between min (16°C) and max (32°C).
- **Thumb**: High-density white/cyan circle with an intense central core and a diffused outer glow ring for precise touch feedback.
- **Flanking Steppers**: Minimal minus and plus pill buttons with tactile press states (slight downward scale `0.96` and inner shadow on tap).

### Connection & Environment Badges
- **Status Pills**: Subdued chips featuring pulsing status dots (green for connected, amber for searching).
- **Metric Cards**: Ghost containers displaying room ambient temperature, humidity, and filter health using soft monochrome typography alongside glowing vector icons.