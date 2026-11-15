import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";

// The style lint (docs/design.md, "Rules the tests enforce"; docs/design-audit.md, section 12):
// no screen or component sets a colour, a font size, a font weight, a corner radius or a border
// width of its own. Everything comes from theme.ts. A new exception needs the owner's approval and
// an entry in docs/design.md, "Approved exceptions".

const ROOT = __dirname;

/** Files allowed to break a rule, each with the rule and the reason (design.md, "Approved exceptions"). */
const EXCEPTIONS: Record<string, { rule: string; reason: string }[]> = {
  "components/ds/Cover.tsx": [
    {
      rule: "hex",
      reason: "The cover illustration palette: an illustration, not UI colour (contrast is tested)",
    },
  ],
};

const RULES: { name: string; pattern: RegExp; hint: string }[] = [
  { name: "hex", pattern: /["'`]#[0-9a-fA-F]{3,8}["'`]/, hint: "a colour belongs in theme.ts" },
  { name: "rgb", pattern: /["'`]rgba?\(/, hint: "an overlay colour belongs in theme.ts" },
  { name: "fontSize", pattern: /\bfontSize\s*:/, hint: "spread a `type` token instead" },
  { name: "lineHeight", pattern: /\blineHeight\s*:/, hint: "spread a `type` token instead" },
  { name: "fontFamily", pattern: /\bfontFamily\s*:/, hint: "the app uses the system font" },
  {
    name: "fontWeight",
    pattern: /\bfontWeight\s*:\s*["'`]?\d/,
    hint: "use `weight.*` from theme.ts",
  },
  {
    name: "borderRadius",
    pattern: /\bborder(?:[A-Za-z]*)Radius\s*:\s*[1-9]/,
    hint: "use `radius.*` from theme.ts",
  },
  {
    name: "borderWidth",
    pattern: /\bborder(?:Top|Bottom|Left|Right)?Width\s*:\s*[1-9]/,
    hint: "use `border.*` from theme.ts",
  },
  {
    name: "hairlineWidth",
    pattern: /StyleSheet\.hairlineWidth/,
    hint: "use `border.hairline` from theme.ts",
  },
];

function sources(dir: string): string[] {
  const found: string[] = [];
  for (const name of readdirSync(dir)) {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) {
      found.push(...sources(path));
    } else if (/\.tsx?$/.test(name) && !/\.test\.tsx?$/.test(name) && name !== "theme.ts") {
      found.push(path);
    }
  }
  return found;
}

test("no screen or component defines a colour, type, radius or border of its own", () => {
  const problems: string[] = [];
  for (const file of sources(ROOT)) {
    const name = relative(ROOT, file).split("\\").join("/");
    // Test helpers are not UI.
    if (name.startsWith("testing/")) continue;
    const allowed = new Set((EXCEPTIONS[name] ?? []).map((e) => e.rule));
    readFileSync(file, "utf8")
      .split("\n")
      .forEach((line, n) => {
        if (/^\s*(\/\/|\*|\/\*)/.test(line)) return;
        for (const rule of RULES) {
          if (!allowed.has(rule.name) && rule.pattern.test(line)) {
            problems.push(`${name}:${n + 1} ${rule.name}: ${rule.hint}\n    ${line.trim()}`);
          }
        }
      });
  }
  expect(problems).toEqual([]);
});

test("every exception names a file that exists and a reason", () => {
  for (const [name, list] of Object.entries(EXCEPTIONS)) {
    expect(() => statSync(join(ROOT, name))).not.toThrow();
    for (const e of list) expect(e.reason.length).toBeGreaterThan(10);
  }
});

test("the old shared modules stay deleted", () => {
  for (const gone of [
    "components/ui.tsx",
    "components/Button.tsx",
    "components/ds/BoxField.tsx",
    "components/ds/Dropdown.tsx",
    "components/plan/PlanSummaryCard.tsx",
  ]) {
    expect(() => statSync(join(ROOT, gone))).toThrow();
  }
});
