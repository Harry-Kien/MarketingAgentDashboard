---
trigger: always_on
---

# MarketingAgentDashboard — UI/UX Rules

## 1. Design System Priority (MANDATORY)

Follow this priority order:

1. Existing design system in `dashboard/app.css`
2. Existing UI components and CSS variables
3. Existing layout and interaction patterns
4. Ant Design principles in `docs/design.md`

IMPORTANT:
`docs/design.md` is a REFERENCE, NOT a replacement
design system.

If Ant Design conflicts with the current project
design system, ALWAYS preserve the existing one.

## 2. STRICTLY PROHIBITED

- DO NOT copy Ant Design's default colors into the project.
- DO NOT replace the existing primary or secondary colors.
- DO NOT change global fonts or typography scales.
- DO NOT override existing CSS variables or theme tokens.
- DO NOT globally change button heights or border radii.
- DO NOT replace the existing light/dark theme.
- DO NOT install Ant Design, React, or another UI framework.
- DO NOT redesign unrelated pages or components.
- DO NOT perform large-scale CSS refactoring without approval.

## 3. Allowed Improvements

Use Ant Design principles to improve:

- Information hierarchy and layout organization
- Form structure and field grouping
- Tables, filtering, and search usability
- Navigation and menu organization
- Button hierarchy and destructive action separation
- Loading, error, success, and empty states
- Modal and drawer interaction patterns
- Accessibility and responsive behavior

Reuse existing project components and styles.

## 4. Before Every UI Change

1. Inspect the relevant HTML, JavaScript and CSS.
2. Identify existing CSS variables and components.
3. Determine exactly which UX Backlog issue is being fixed.
4. Preserve existing colors, fonts, spacing conventions,
   and component styling.
5. Make the smallest necessary change.

## 5. Verification

After every UI change:

- Verify that existing theme colors remain unchanged.
- Verify that global CSS variables remain unchanged.
- Verify unrelated pages are unaffected.
- Check desktop and mobile layouts.
- Run relevant regression tests.
- Use Playwright when possible.
- Report any visual regression.

If a requested change requires modifying the global
design system, STOP and ask for approval first.

## 6. Project Safety

- Never modify production database `marketing_agent`.
- Use `kiemthu` for database-backed UI testing.
- Preserve existing RBAC and business logic.
- Do not edit unrelated source files.
- Do not update UX Backlog automatically.
- Do not commit or push without permission.
