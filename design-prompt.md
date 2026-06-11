# Task: Premium design pass on the Realty-AI Telegram Mini App

You are improving the visual design and polish of an existing, working
Telegram Mini App for a real-estate agency. Frontend is React + Tailwind.
This is a design-improvement pass: make it look more premium, more
consistent, and easier to use.

## Goal
Make every screen feel premium, polished, consistent, and demo-ready for
agency owners — while also being clearly easier to use. Refinement and
evolution, not a throwaway rebuild.

## Scope (touch all screens, prioritize as marked)
Screens in frontend/src/screens: Home, Apartments, Analytics, Team,
AgentDetail, Profile, Settings, Invites, Superadmin (+ App.tsx nav).
- TOP PRIORITY, deepest work: Apartments (the property listings — the
  heart of the app) and the first-impression / onboarding experience
  (what a brand-new user sees first: first screen, empty states,
  profile setup).
- HIGH: Home, Analytics.
- Everyone else: a consistency pass so nothing looks out of place.

## Visual direction — "evolve the palette"
Keep the soul of the current design system (indigo minimalism + Manrope
font), but evolve it to feel more premium:
- Keep the minimal, clean feel and Manrope typography.
- You MAY introduce richer accent colors, refined gradients, and a
  deeper/more sophisticated palette for a premium look.
- Tighten hierarchy, spacing, depth (layered soft shadows), and
  typographic rhythm across all screens.
- Centralize via existing tokens: frontend/src/index.css (CSS variables,
  light + .dark themes, @font-face) and frontend/tailwind.config.js.
  Build screens from the shared components in
  frontend/src/components/ui.tsx — extend these, don't fork per-screen.

## Property cards (Apartments) — IMPORTANT constraint
Do NOT change the card layout or its overall size. The ONLY card change:
make the property PHOTO visually bigger / more prominent WITHIN the
existing card footprint (give the image more weight without enlarging
the card). Everything else about the card stays as-is.

## Telegram-native features
- Use Telegram native buttons (MainButton / BackButton / SettingsButton)
  where they fit better than custom in-page buttons.
- Add subtle haptic feedback on key actions (taps, toggles, success,
  error). A haptic helper already exists in frontend/src/telegram.
- BUT keep the app self-contained: keep our OWN indigo brand look and our
  OWN light/dark theme toggle. Do NOT auto-follow the user's Telegram
  theme or accent color.

## Motion — subtle & purposeful
Smooth screen transitions, press/tap feedback, skeleton loaders, gentle
fades. Premium but fast — nothing that delays the user or feels gimmicky.
Polish loading, empty, and success/error states everywhere.

## Rollback — I must be able to return to the old version
Before changing ANY design code, create a fresh, clearly-named backup of
the current design so I can fully restore it later if I don't like the
new look:
- Commit the current state, then create a new git tag for it, e.g.
  `design-backup-<today's date>` (do NOT reuse the old
  design-backup-2026-06-09 tag — that's from a previous redesign).
- Also keep a physical copy of the current frontend/src under
  backups/design/src_<today's date>/ (matching how the previous backup
  was stored).
- At the very end, give me ONE simple, copy-paste instruction (in plain
  language) to roll everything back to that backup if I don't like the
  result. Restore must be done safely via `git revert` + redeploy
  (NOT git reset / force-push — the server pulls with `git pull --ff-only`
  and a force-push would break it).
- Confirm the backup exists BEFORE you start editing.

## Guardrails (freedom to improve, but keep it working)
- You have FREE REIN: change styling, layout, components, structure, and
  flows as needed to achieve the best result. This includes small UX
  fixes (reorder steps, merge screens, simplify interactions) AND deeper
  refactors of components or structure when they clearly improve the app.
- The ONE rule: every existing feature must still work. Don't remove or
  break functionality, data, or API contracts — improve how it looks and
  flows, not what it does.
- STRICT CSP: no external fonts, CDNs, or remote assets. Local assets
  only (fonts live in frontend/public/fonts, loaded via @font-face with
  /fonts/...). The Caddyfile CSP blocks anything external.
- MULTILINGUAL: the UI ships in 3 languages (ru / uz / en). All three
  must keep working; any new copy needs i18n keys for all three.
- THEMES: keep both light and .dark themes fully working.
- Prefer reusing/extending frontend/src/components/ui.tsx so changes stay
  consistent — but you may restructure it if that's better.
- Since this is a bigger-scope pass, keep diffs reviewable: explain what
  changed and why, screen by screen.

## Working approach
1. FIRST create the rollback backup (tag + physical copy) and confirm it.
2. Read index.css, tailwind.config.js, and ui.tsx to learn the current
   tokens and components.
3. Propose the palette evolution + shared-component upgrades FIRST
   (tokens, shadows, accents, type scale), since these cascade to every
   screen.
4. Then apply screen-by-screen, in priority order, reusing the upgraded
   components.
5. Keep diffs focused and explain what changed and why per screen.
6. At the end, give me the plain-language rollback instruction.
