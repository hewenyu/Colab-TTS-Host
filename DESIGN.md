---
name: 声间 · Colab TTS Host
description: A private voice workspace with mineral-white surfaces, an ink-navy rail, and precise cobalt selection.
colors:
  ink: '#20313d'
  muted: '#62717d'
  line: '#dce3e8'
  ground: '#f3f6f8'
  paper: '#fff'
  accent: '#2656c9'
  accent-soft: '#edf2ff'
  nav: '#182d3c'
  danger: '#a92b38'
  accent-hover: '#1b44aa'
  accent-active: '#14378d'
  focus: '#83a9ff'
  field-border: '#cdd8e1'
  secondary-border: '#cbd6df'
  nav-active: '#2b465a'
  nav-text: '#bdcbd6'
typography:
  headline:
    fontSize: 28px
    fontWeight: 650
    lineHeight: 1.35
    letterSpacing: -0.025em
  title:
    fontSize: 16px
    fontWeight: 650
  subheading:
    fontSize: 14px
    fontWeight: 600
  body:
    fontFamily: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif
    fontSize: 14px
    fontWeight: 400
    lineHeight: 1.6
  editor:
    fontSize: 15px
    lineHeight: 1.9
  label:
    fontSize: 12px
    fontWeight: 550
  metadata:
    fontSize: 11px
  button:
    fontSize: 14px
    fontWeight: 550
rounded:
  badge: 5px
  icon: 6px
  control: 7px
  row: 8px
  surface: 10px
spacing:
  '6': 6px
  '8': 8px
  '12': 12px
  '16': 16px
  '18': 18px
  '20': 20px
  '22': 22px
  '24': 24px
  '26': 26px
  '28': 28px
  '30': 30px
  '32': 32px
  '40': 40px
components:
  button-primary:
    backgroundColor: '{colors.accent}'
    textColor: '{colors.paper}'
    typography: '{typography.button}'
    rounded: '{rounded.control}'
    padding: 9px 19px
  button-primary-hover:
    backgroundColor: '{colors.accent-hover}'
  button-primary-active:
    backgroundColor: '{colors.accent-active}'
  button-secondary:
    backgroundColor: '{colors.paper}'
    textColor: '{colors.ink}'
    typography: '{typography.button}'
    rounded: '{rounded.control}'
    padding: 9px 19px
  button-text:
    textColor: '{colors.accent}'
    padding: 4px 0
  button-icon:
    textColor: '{colors.muted}'
    rounded: '{rounded.icon}'
    padding: 8px
  input:
    backgroundColor: '{colors.paper}'
    textColor: '{colors.ink}'
    rounded: '{rounded.control}'
    padding: 10px 12px
    width: 100%
  navigation:
    textColor: '{colors.nav-text}'
    rounded: '{rounded.control}'
    padding: 12px 13px
  navigation-active:
    backgroundColor: '{colors.nav-active}'
    textColor: '{colors.paper}'
  badge:
    backgroundColor: '#f0f3f6'
    textColor: '#566876'
    rounded: '{rounded.badge}'
    padding: 3px 9px
    typography: '{typography.metadata}'
  card:
    backgroundColor: '{colors.paper}'
    rounded: '{rounded.surface}'
    padding: 26px
  voice-row:
    textColor: '{colors.ink}'
    rounded: '{rounded.row}'
    padding: 14px 12px
    width: 100%
  voice-row-selected:
    backgroundColor: '{colors.accent-soft}'
  job-state:
    backgroundColor: '#eef1f5'
    textColor: '#536575'
    rounded: '{rounded.badge}'
    padding: 3px 9px
    typography: '{typography.metadata}'
---

# Design System: 声间 · Colab TTS Host

## Overview

**Creative North Star: "The Private Listening Room"**

Mineral-white work surfaces sit beside an ink-navy navigation rail. Cobalt identifies actions and selected voices; quiet borders and compact metadata keep the workspace readable while recordings, transcripts, and output remain the main material.

The implemented character is restrained and operational: familiar browser controls, generous space around the editor, and closely organized rows for voices, materials, and training records. This is a code-derived record of the shipped interface, not an approved image composition. The North Star is a descriptive name for the implemented world, not a separately approved brand claim.

**Key Characteristics:**
- Mineral-white surfaces with an ink-navy navigation anchor.
- Cobalt action and selection states, supported by text and borders.
- Compact record metadata inside generously spaced work areas.
- Native audio controls paired with a waveform derived from actual samples.

## Colors

The palette uses a cool mineral ground, white work surfaces, ink text, and a concentrated cobalt accent. Frontmatter values are normative; CSS custom-property names remain intact where present.

### Primary
- **Precise Cobalt** (`accent`): primary actions, links, caret, and selected voice accents. Its hover and active steps deepen the same action.
- **Cobalt Wash** (`accent-soft`): selected voice row fill, reinforced by a border and checkmark.
- **Focus Blue** (`focus`): the shared keyboard outline, distinct from selected state.

### Neutral
- **Ink** (`ink`): principal text.
- **Slate** (`muted`): supporting copy, metadata, and quiet controls.
- **Mineral Ground** (`ground`): the page canvas.
- **Paper** (`paper`): editable and working surfaces.
- **Quiet Rule** (`line`): separators and container borders.
- **Ink Navy** (`nav`): navigation anchor; `nav-text` and `nav-active` preserve the rail's own tonal hierarchy.
- **Field Stroke** (`field-border`) and **Secondary Stroke** (`secondary-border`): distinguish editable controls and secondary buttons from white containers.

Danger red is reserved for field failures and error notices. Success and running-state fills are local semantic treatments documented in component snippets, not a second decorative accent palette.

**The Cobalt Selection Rule.** Use the cobalt family for actionable controls and selected voice states; retain text and structural cues so color is never the only identifier.

## Typography

**Body Font:** native platform sans-serif with explicit Simplified Chinese fallbacks, as recorded in the body token. Controls inherit it. There is no independent mono face or loaded display font.

**Character:** a compact, legible Chinese interface with weight, space, and scale carrying hierarchy. Numeric counts, material cells, and character counters use tabular numerals where available.

### Hierarchy
- **Headline:** page heading; the recorded desktop scale reduces to 25px at the intermediate breakpoint and 22px on mobile.
- **Title:** section headings.
- **Subheading:** result and record headings.
- **Body:** normal interface and explanatory copy.
- **Editor:** the speech composer, with relaxed line spacing.
- **Label:** field names and compact form guidance.
- **Metadata:** counts, voice versions, small badges, and output details.

The existing system-stack page headings are implementation evidence, not a new display typography prescription. The small uppercase English brand descriptor is a brand lockup detail; do not generalize it into page kickers.

## Layout

Desktop uses a sticky, viewport-height navigation rail (216px) and a flexible workspace. The top bar is 76px high. Main content has a 1500px maximum width and padding of 36px 40px 16px. The studio is a bordered two-column container with a minimum 240px voice column and proportional 0.8fr / 1.55fr widths; its minimum height is 590px. The library and composer have independently padded interiors rather than nested floating cards.

At widths up to 1100px, the rail narrows to 184px, horizontal main padding becomes 24px, and the connection form stacks. At widths up to 760px, the rail becomes a compact top navigation band, the top bar becomes 52px high, main padding becomes 24px 18px 12px, and the studio, form grids, and draft rows stack. Voice rows scroll inside a 270px maximum-height list. Mobile material rows retain selection, transcript, and audition; duration and date move under the transcript, with a fixed 62px audition column. At widths from 1600px, main top padding increases to 48px and studio minimum height to 640px.

Spacing follows the observed compact 6–12px control rhythm and wider 18–40px grouping rhythm; it is not a strict single-base grid. Long voice names and transcripts wrap. Output actions and metadata wrap rather than force viewport overflow.

## Elevation & Depth

Depth is primarily tonal: a cool ground, white containers, a slightly tinted voice library, and quiet rules. The composite studio carries a diffuse ambient shadow. A stronger shadow distinguishes the fixed material-audition player from document content. Neither shadow is a hard offset treatment.

### Shadow Vocabulary
- **Studio ambient:** `0 12px 36px #132c4010` for the composite studio surface.
- **Floating audio:** `0 5px 24px #132c4033` for the fixed material preview player.

**The Quiet Surface Rule.** Use tonal separation and fine borders for ordinary containers; reserve the existing diffuse shadow for the composite studio and floating audio preview.

## Shapes

Corners are gently rounded: surface, row, control, icon-button, and badge radii are recorded in frontmatter. Borders are generally one pixel; the upload region uses a dashed stroke. Voice marks are compact rounded squares. Connection indicators are circular. The floating native-audio wrapper is more rounded (20px) because it is a distinct player, not a general card template.

Icons use simple inline SVG strokes with rounded ends and joins, normally 20px with a 1.6px stroke. The plus character in the add-voice button is an existing exception, not the basis of the icon vocabulary.

## Components

### Buttons

Quiet, direct actions with a clear primary choice. Primary and secondary controls share a 42px minimum height, compact horizontal padding, and a softly rounded shape. Primary buttons use cobalt with deeper hover and pressed states. Secondary controls use paper and ink with a fine border; hover adds a cool tint. Text actions use cobalt without a container and underline on hover. Icon buttons use a transparent background and reveal a neutral fill on hover. Disabled buttons and inputs reduce opacity to 0.5 and use a not-allowed cursor.

Interactive elements transition background, border, and text color over 0.18s with ease-out. Focus-visible uses a 3px outline with a 3px offset. Reduced-motion preference disables transitions and smooth scrolling. File selection exposes the same outline through focus-within.

### Chips

Compact badges identify voice/version and job state. They are informational, not filter pills. The selected voice badge truncates with ellipsis, reducing its maximum width from 200px to 140px on mobile. Job state chips retain explicit labels alongside gray, blue, green, or red semantic treatments.

### Cards / Containers

White forms and material containers use a quiet border and surface radius. Forms use 26px desktop padding; mobile forms reduce to 20px. Material containers use 24px desktop padding and 20px 14px on mobile. Only the composite studio uses the ambient shadow. Job records use the row radius, 22px 24px padding, and a rule separating their current stage.

### Inputs / Fields

Native input, textarea, and select controls use paper, ink, a fine field stroke, control radius, and a 42px minimum height. Search inputs have a cool tinted fill. Textareas resize vertically; the speech editor has 16px padding and a 200px minimum height. Labels remain visible; placeholders supplement them. Errors appear as adjacent danger-colored alert text. Consent controls retain native checkbox behavior with cobalt accent.

### Navigation

Desktop navigation is a vertical set of links in the navy rail. Current location uses a lighter navy fill and white text, exposed through aria-current. Hover uses an intermediate navy fill. On mobile, links share one horizontal row with smaller icons and text; connection state stays at the top right. The skip link appears on focus and transfers focus to the main workspace without changing the selected hash route.

### Voice Rows and Audio Output

Voice rows combine a square SVG mark, name, reference-or-fine-tuned metadata, and a selected check. The selected row has a cobalt wash and fine blue border, exposed through aria-pressed. The output area is separated by a quiet rule and carries its own voice/version identity. The 76px waveform surface renders amplitudes derived from audio; its empty state is a baseline. Native audio controls, download, and export actions remain explicit.

## Do's and Don'ts

### Do:
- **Do** retain a visible focus outline on interactive controls and a keyboard skip link to the workspace.
- **Do** preserve selected voice and output version identity beside their respective controls.
- **Do** move duration and date beneath material transcripts on narrow screens so the audition column stays available.
- **Do** derive waveform marks from real audio samples and use a flat baseline when no samples exist.
- **Do** show capability, error, and job states in words as well as color.

### Don't:
- **Don't** use decorative waveform samples to imply generated audio.
- **Don't** replace real job stages with invented progress or ornamental dashboard metrics.
- **Don't** turn transient notices, disabled controls, or test data into permanent content or visual identity.
- **Don't** extend the current system-stack page heading or literal plus-sign icon into a new display-font or icon rule; these remain implementation exceptions.
