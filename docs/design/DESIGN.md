---
name: KAgent Precision Workspace
description: A calm, precise enterprise AI workspace with role-aware operational depth.
colors:
  accent: "#2563EB"
  accent-hover: "#1D4ED8"
  canvas: "#F6F8FB"
  surface: "#FFFFFF"
  surface-subtle: "#F1F4F8"
  ink: "#171A21"
  text-secondary: "#5F6673"
  text-muted: "#7B8494"
  border: "#DDE2EA"
  border-strong: "#C7CED9"
  success: "#16875B"
  warning: "#9A6700"
  danger: "#C93747"
typography:
  headline:
    fontFamily: "Inter, ui-sans-serif, system-ui, PingFang SC, Microsoft YaHei, sans-serif"
    fontSize: "24px"
    fontWeight: 650
    lineHeight: 1.25
    letterSpacing: "-0.02em"
  title:
    fontFamily: "Inter, ui-sans-serif, system-ui, PingFang SC, Microsoft YaHei, sans-serif"
    fontSize: "16px"
    fontWeight: 650
    lineHeight: 1.4
  body:
    fontFamily: "Inter, ui-sans-serif, system-ui, PingFang SC, Microsoft YaHei, sans-serif"
    fontSize: "14px"
    fontWeight: 400
    lineHeight: 1.65
  label:
    fontFamily: "Inter, ui-sans-serif, system-ui, PingFang SC, Microsoft YaHei, sans-serif"
    fontSize: "12px"
    fontWeight: 550
    lineHeight: 1.4
rounded:
  control: "6px"
  surface: "8px"
  overlay: "10px"
spacing:
  xs: "4px"
  sm: "8px"
  md: "12px"
  lg: "16px"
  xl: "24px"
  page: "28px"
components:
  button-primary:
    backgroundColor: "{colors.accent}"
    textColor: "{colors.surface}"
    typography: "{typography.label}"
    rounded: "{rounded.control}"
    padding: "9px 14px"
  button-primary-hover:
    backgroundColor: "{colors.accent-hover}"
    textColor: "{colors.surface}"
    typography: "{typography.label}"
    rounded: "{rounded.control}"
    padding: "9px 14px"
  input:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    typography: "{typography.body}"
    rounded: "{rounded.surface}"
    padding: "12px 14px"
  nav-selected:
    backgroundColor: "{colors.surface-subtle}"
    textColor: "{colors.accent}"
    typography: "{typography.label}"
    rounded: "{rounded.control}"
    padding: "8px 10px"
---

# Design System: KAgent Precision Workspace

## Overview

**Creative North Star: "The Precision Workspace"**

KAgent is designed for focused work under normal office lighting. The system is light-first, cool-neutral, and deliberately quiet. It borrows Linear's precision without adopting a developer-only tone: alignment is exact, state is explicit, and interactions remain familiar.

Employee surfaces prioritize reading comfort and task continuity. Operational surfaces become denser through compact rows, tables, and status summaries, not through smaller unreadable type or decorative chrome.

**Key Characteristics:**

- Light-first cool neutral surfaces with one controlled blue accent.
- Fixed product typography with strong Chinese and Latin legibility.
- Flat by default, using lines and tonal layers before shadows.
- Compact navigation and controls with generous reading width.
- State motion limited to feedback and transitions.

## Colors

The palette is a cool precision neutral system with blue reserved for selection, focus, links, and primary actions.

### Primary

- **Decision Blue:** The only interactive accent. It marks active navigation, focus, links, and primary actions.

### Neutral

- **Workspace Canvas:** The application background behind fixed product surfaces.
- **Primary Surface:** Conversation, table, and content surfaces.
- **Quiet Surface:** Selected rows, tool activity, filters, and secondary controls.
- **Primary Ink:** Main headings and body text.
- **Secondary Text:** Supporting descriptions and metadata.
- **Structural Border:** Dividers, table structure, and field boundaries.

### Named Rules

**The One Accent Rule.** Blue occupies less than 10% of a screen and is never decorative.

**The Semantic Status Rule.** Success, warning, and danger colors always appear with text or an icon. Color never carries meaning alone.

## Typography

**Display Font:** Inter with system UI and Chinese system fallbacks  
**Body Font:** Inter with system UI and Chinese system fallbacks  
**Label/Mono Font:** JetBrains Mono for IDs and numeric diagnostics only

**Character:** A single neutral sans family creates the precise product feel. Chinese text uses native system glyphs to avoid mismatched fallback rendering. Headings are weighted, not oversized.

### Hierarchy

- **Headline** (650, 24px, 1.25): Page titles only.
- **Title** (650, 16px, 1.4): Section and response headings.
- **Body** (400, 14px, 1.65): Conversation and explanatory content, capped at 72 characters per line.
- **Label** (550, 12px, 1.4): Navigation, controls, metadata, and compact table labels.
- **Data** (500, 12-13px): IDs, timestamps, latency, and counters with tabular numerals.

### Named Rules

**The Product Scale Rule.** Product type uses fixed sizes. No fluid headings, tracked uppercase labels, or display typography inside the app shell.

## Elevation

The system is flat by default. Depth comes from canvas-to-surface contrast, dividers, and selected-state tinting. Shadows are reserved for overlays, menus, and the focused composer.

### Shadow Vocabulary

- **Overlay:** A compact cool shadow for menus and dialogs only.
- **Focus Lift:** A minimal blue-tinted shadow used while the message composer has focus.

### Named Rules

**The Structural Depth Rule.** If spacing or a divider can explain hierarchy, a shadow is prohibited.

## Components

### Buttons

- **Shape:** Compact gently rounded controls (6px).
- **Primary:** Decision Blue with white text and 9px by 14px padding.
- **Hover / Focus:** Darker blue on hover; a visible 2px focus ring outside the control.
- **Secondary / Ghost:** White or transparent surfaces with structural borders and primary ink.

### Chips

- **Style:** Quiet surface, secondary text, 1px border, 6px radius.
- **State:** Selected chips use a pale blue fill and blue text without becoming pills.

### Cards / Containers

- **Corner Style:** 8px for meaningful contained objects only.
- **Background:** Primary Surface or Quiet Surface.
- **Shadow Strategy:** Flat at rest.
- **Border:** One structural border where grouping requires it.
- **Internal Padding:** 16px for compact panels, 20-24px for primary reading surfaces.

### Inputs / Fields

- **Style:** White surface, 1px border, 8px radius, readable placeholder.
- **Focus:** Blue border plus a restrained focus lift.
- **Error / Disabled:** Text and icon accompany semantic color; disabled controls retain legible labels.

### Navigation

The sidebar is 280px on desktop and becomes a drawer on smaller screens. Sections are grouped by task: Workbench and Management. Active state uses a quiet blue tint, blue label, icon, and a restrained 3px edge marker.

### Execution Activity

Tool use appears as a compact expandable status row containing action, source count, duration, and final status. It never exposes raw model reasoning.

## Do's and Don'ts

### Do:

- **Do** prioritize the answer and source evidence in the employee workspace.
- **Do** use compact, familiar table and filter controls on operational pages.
- **Do** provide loading skeletons, actionable empty states, inline errors, and keyboard focus.
- **Do** preserve existing routes, labels, data contracts, and destructive confirmations.
- **Do** collapse the sidebar and reflow tables deliberately below 768px.

### Don't:

- **Don't** turn the product into a technical monitoring dashboard.
- **Don't** use generic AI purple gradients, glow, glassmorphism, or cyberpunk styling.
- **Don't** expose raw chain-of-thought or hidden model reasoning.
- **Don't** build card walls, oversized headings, or decorative status indicators.
- **Don't** replace standard controls with unfamiliar interactions for novelty.
- **Don't** pair a wide shadow with a border on the same surface.
